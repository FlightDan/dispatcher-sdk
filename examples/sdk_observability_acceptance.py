"""Independent installed SDK consumer with retained local acceptance evidence.

Run outside the checkout with the candidate wheel installed::

    python sdk_observability_acceptance.py --evidence-dir /tmp/sdk-a16

The local tool/backend fixtures execute real Python processes. They need no
provider credentials. Cleanup recovery preserves recovery_required: disposal
confirmation is not an external-effect recovery decision.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import queue
import subprocess
import sys
import threading
import time
import traceback
import uuid

import dispatcher_sdk
from dispatcher_sdk import BudgetEnvelope, Dispatcher, ObservationOptions, RecoveryRequiredError, StallPolicy
from dispatcher_sdk.execution_kernel import (
    ChildExecutionError, HandlerExecutionError, SandboxHandler, SandboxObservation, SandboxSpec,
)

OPTIONS = ObservationOptions(flush_interval=.1)


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.writing-' + str(os.getpid()))
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def mark(root, name, **value):
    save(Path(root) / (name + '.json'), {'wall': time.time(), 'monotonic': time.monotonic(),
        'pid': os.getpid(), 'interpreter': sys.executable, 'sdk_import': dispatcher_sdk.__file__, **value})


def call(root, phase, **details):
    with (Path(root) / 'calls.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'phase': phase, 'pid': os.getpid(), 'at': time.time(), **details}) + '\n')


def await_value(read, predicate=bool, *, seconds=6):
    deadline = time.monotonic() + seconds
    while True:
        value = read()
        if predicate(value):
            return value
        if time.monotonic() >= deadline:
            raise TimeoutError('acceptance condition not reached: ' + repr(value))
        time.sleep(.02)


def read_json(path):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def local_tool(root, payload):
    root = Path(root)
    envelope = BudgetEnvelope.from_dict(payload['budget'])
    mark(root, 'tool-received', input=payload['input'], envelope=envelope.to_dict(),
         budget=envelope.view().to_dict())
    call(root, 'tool', input=payload['input'])
    if payload['mode'] == 'blocked':
        while True:
            time.sleep(.1)
    if payload['mode'] == 'failure':
        written = os.write(2, b'local tool refused the original input')
        mark(root, 'tool-write-error', stream='stderr', byte_count=written)
        return 17
    written = os.write(1, b'A\xff')
    mark(root, 'tool-write-first', stream='stdout', byte_count=written)
    while True:
        remaining = envelope.view().remaining_work_seconds
        if remaining is None or remaining <= 0:
            mark(root, 'tool-release-expired', budget=envelope.view().to_dict())
            return 18
        if (root / 'release-tool').exists():
            break
        time.sleep(min(.02, remaining))
    written = os.write(1, b'BC')
    mark(root, 'tool-write-last', stream='stdout', byte_count=written)
    return 0


def child(payload, context):
    root = Path(payload['root'])
    call(root, 'child', execution_id=context.command.execution_id)
    context.activity.enable_stream('stdout')
    context.activity.enable_stream('stderr')
    tool_budget = context.derive_budget(source='tool', origin_id='local-tool',
                                       timeout_seconds=payload['tool_timeout'], reserve_seconds=.1)
    supplied = {'input': payload['input'], 'mode': payload['mode'], 'budget': tool_budget.to_dict()}
    mark(root, 'child-entered', execution_id=context.command.execution_id,
         budget=context.budget.to_dict(), tool_budget=tool_budget.to_dict())
    process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--fixture-tool',
        str(root), json.dumps(supplied)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    context.activity.observe_process(process, role='local-tool')
    context.activity.tool('request')
    assert process.stdout is not None and process.stderr is not None
    chunks = queue.Queue()
    captured = {'stdout': bytearray(), 'stderr': bytearray()}

    def collect(stream, pipe):
        try:
            while chunk := pipe.read1(65536):
                chunks.put((stream, chunk, None))
        except Exception as error:
            chunks.put((stream, None, error))
        finally:
            chunks.put((stream, None, None))

    collectors = [threading.Thread(target=collect, args=(stream, pipe), daemon=True)
                  for stream, pipe in (('stdout', process.stdout), ('stderr', process.stderr))]
    for collector in collectors:
        collector.start()
    first_reported = False

    def record(stream, chunk):
        nonlocal first_reported
        captured[stream].extend(chunk)
        context.activity.report_bytes(stream, chunk)
        if payload['mode'] == 'success' and stream == 'stdout' and not first_reported:
            if len(captured['stdout']) >= 2:
                mark(root, 'first-reported', bytes=list(captured['stdout'][:2]))
                first_reported = True

    try:
        with context.activity.wait('tool_response', target='local-tool',
                deadline_at=tool_budget.view().effective_work_deadline_at):
            closed = set()
            while len(closed) != 2:
                remaining = tool_budget.view().remaining_work_seconds
                if remaining is None or remaining <= 0:
                    raise subprocess.TimeoutExpired(process.args, 0)
                try:
                    stream, chunk, collection_error = chunks.get(timeout=min(.02, remaining))
                except queue.Empty:
                    continue
                if collection_error is not None:
                    raise collection_error
                if chunk is None:
                    closed.add(stream)
                else:
                    record(stream, chunk)
            remaining = tool_budget.view().remaining_work_seconds
            if remaining is None or remaining <= 0:
                raise subprocess.TimeoutExpired(process.args, 0)
            process.wait(timeout=remaining)
            completed_budget = tool_budget.view().to_dict()
            if not completed_budget['remaining_work_seconds']:
                raise subprocess.TimeoutExpired(process.args, 0)
            if payload['mode'] == 'blocked':
                raise AssertionError('blocked fixture unexpectedly returned')
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
        mark(root, 'tool-stopped', returncode=process.returncode, budget=tool_budget.view().to_dict())
        raise HandlerExecutionError('execution_deadline_exhausted', 'local tool reached its work cutoff',
                                    details=tool_budget.view().to_dict())
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        for collector in collectors:
            collector.join(timeout=2)
        while not chunks.empty():
            stream, chunk, _ = chunks.get_nowait()
            if chunk is not None:
                captured[stream].extend(chunk)
        (root / 'received.stdout').write_bytes(captured['stdout'])
        (root / 'received.stderr').write_bytes(captured['stderr'])
        process.stdout.close()
        process.stderr.close()
    raw, error = bytes(captured['stdout']), bytes(captured['stderr'])
    context.activity.tool('response')
    mark(root, 'tool-returned', returncode=process.returncode, stdout=list(raw), stderr=error.decode(),
         completed_budget=completed_budget)
    if process.returncode:
        raise HandlerExecutionError('local_tool_denied', error.decode(),
                                    details={'returncode': process.returncode, 'input': payload['input']})
    progress_timeout = min(1.0, context.budget.remaining_work_seconds)
    mark(root, 'child-progress-call', timeout=progress_timeout, budget=context.budget.to_dict())
    receipt = context.activity.progress('child-consumed-tool', timeout=progress_timeout)
    replay = None
    if receipt.get('state') == 'confirmed':
        replay_timeout = min(1.0, context.budget.remaining_work_seconds)
        mark(root, 'child-progress-replay-call', timeout=replay_timeout, budget=context.budget.to_dict())
        replay = context.activity.progress('child-consumed-tool', timeout=replay_timeout)
    else:
        mark(root, 'child-progress-unverified', receipt=receipt)
    return {'input': payload['input'], 'bytes': list(raw), 'budget': context.budget.to_dict(),
            'progress': receipt, 'replay': replay}


def parent(payload, context):
    root = Path(payload['root'])
    call(root, 'parent', execution_id=context.command.execution_id)
    before = context.budget.to_dict()
    try:
        result = context.children.run('child', payload, request_id='one-original-child',
                                      timeout_seconds=payload['child_timeout'])
    except ChildExecutionError as error:
        return {'child_error': error.result, 'code': error.code, 'before': before,
                'after': context.budget.to_dict()}
    progress_timeout = min(1.0, context.budget.remaining_work_seconds)
    mark(root, 'parent-progress-call', timeout=progress_timeout, budget=context.budget.to_dict())
    progress = context.activity.progress('parent-consumed-child', timeout=progress_timeout)
    if progress.get('state') != 'confirmed':
        mark(root, 'parent-progress-unverified', receipt=progress)
    return {'child': result, 'before': before, 'after': context.budget.to_dict(), 'progress': progress}


def silent(payload, context):
    root = Path(payload['root'])
    call(root, 'silent', execution_id=context.command.execution_id)
    context.activity.enable_stream('stdout')
    script = "import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); f=p.open('ab',buffering=0)\nwhile True: f.write(b'.'); time.sleep(.03)"
    process = subprocess.Popen([sys.executable, '-c', script, str(root / 'descendant-ticks')])
    context.activity.observe_process(process, role='silent-descendant')
    mark(root, 'silent-entered', execution_id=context.command.execution_id, child_pid=process.pid,
         budget=context.budget.to_dict())
    process.wait()
    return {'unexpected': 'silent descendant returned'}


for handler in (parent, child, silent):
    handler.__execution_kernel_revision__ = 'sdk-a16-local-consumer-v1'


def parent_child_case(root, mode):
    root.mkdir(parents=True, exist_ok=True)
    payload = {'root': str(root), 'input': 'original-consumer-input', 'mode': mode,
               'child_timeout': 8, 'tool_timeout': 4 if mode != 'blocked' else 1.2}
    save(root / 'configuration.json', {'payload': payload, 'execution_timeout': 20,
                                     'caller_timeout': 25, 'child_capacity': 1})
    with Dispatcher(root / 'application.sqlite3', {'parent': parent, 'child': child},
                    isolation_mode='process', child_capacity=1, observation_options=OPTIONS) as app:
        task = app.submit('parent', payload, request_id='parent-' + mode, timeout_seconds=20)
        if mode == 'success':
            first = await_value(lambda: read_json(root / 'first-reported.json'), seconds=12)
            entered = read_json(root / 'child-entered.json')
            partial = await_value(lambda: app.runtime.observe(entered['execution_id'], timeout=.5),
                lambda value: value.get('metrics', {}).get('stdout_bytes', {}).get('count', 0) >= 2, seconds=3)
            save(root / 'partial-observation.json', partial)
            check(not (root / 'tool-write-last.json').exists(), 'tool completed before partial observation')
            (root / 'release-tool').touch()
            check(first['bytes'] == [65, 255], 'first raw bytes differ')
        result = task.wait(timeout=25)
        observation = task.observe()
        save(root / 'caller-result.json', result)
        save(root / 'parent-observation.json', observation)
        save(root / 'events.json', task.events())
        entered = read_json(root / 'child-entered.json')
        received = read_json(root / 'tool-received.json')
        if entered:
            child_observation = app.runtime.observe(entered['execution_id'])
            save(root / 'child-observation.json', child_observation)
        check(result['status'] == 'succeeded', 'parent did not return its causal child outcome')
        check(received['input'] == payload['input'], 'original input did not reach local tool')
        check(received['envelope'] == entered['tool_budget'], 'tool received a different budget')
        calls = [json.loads(line) for line in (root / 'calls.jsonl').read_text().splitlines()]
        check([item['phase'] for item in calls] == ['parent', 'child', 'tool'],
              'business was replayed or did not reach the consumer')
        check(len({item['pid'] for item in calls}) == 3 and os.getpid() not in {item['pid'] for item in calls},
              'parent/child/tool did not execute in distinct real processes')
        check(entered['execution_id'] == child_observation['identity']['execution_id'],
              'observed a different child identity')
        value = result['value']
        check(value['after']['remaining_work_seconds'] <= value['before']['remaining_work_seconds'],
              'parent budget increased')
        if mode == 'success':
            returned = value['child']['value']
            check(returned['bytes'] == [65, 255, 66, 67], 'caller lost unframed output')
            check(returned['progress'].get('state') == 'confirmed'
                  and returned['progress'].get('advanced') is True
                  and (returned['replay'] or {}).get('state') == 'confirmed'
                  and (returned['replay'] or {}).get('advanced') is False,
                  'progress confirmation or replay failed: ' + json.dumps(
                      {'progress': returned['progress'], 'replay': returned['replay']}))
            check(value['progress'].get('state') == 'confirmed' and value['progress'].get('advanced') is True,
                  'parent progress confirmation failed: ' + json.dumps(value['progress']))
            check(child_observation['metrics']['stdout_bytes']['count'] == 4, 'persisted output missing')
        else:
            error = value['child_error']['error']
            check(error['code'] == ('local_tool_denied' if mode == 'failure' else 'execution_deadline_exhausted'),
                  'caller lost original child error')
            if mode == 'failure':
                check(error['message'] == 'local tool refused the original input' and error['details']['returncode'] == 17,
                      'original local tool failure changed')
            else:
                check(error['details']['limiting_source'] == 'tool', 'shortest tool budget was not limiting')
                stopped = read_json(root / 'tool-stopped.json')
                check(stopped is not None and stopped['returncode'] is not None
                      and stopped['budget']['remaining_work_seconds'] == 0
                      and stopped['budget']['remaining_hard_seconds'] > 0,
                      'tool containment did not finish within its original cleanup reserve')


def silence_cancel_case(root):
    root.mkdir(parents=True, exist_ok=True)
    save(root / 'configuration.json', {'execution_timeout': 12, 'caller_timeout': 15,
        'stall_sample': .2, 'stall_windows': 2, 'callback_capacity': 1})
    received = []
    with Dispatcher(root / 'application.sqlite3', {'silent': silent}, isolation_mode='process',
                    observation_options=OPTIONS) as app:
        def consume(notice):
            received.append(notice)
            save(root / 'notice.json', notice)
        app.subscribe_stalls(consume)
        task = app.submit('silent', {'root': str(root)}, request_id='silent-once', timeout_seconds=12)
        task.watch_stall(StallPolicy('silent-progress', sample_interval=.2, consecutive_windows=2))
        await_value(lambda: read_json(root / 'silent-entered.json'), seconds=6)
        try:
            task.wait(timeout=.05)
        except TimeoutError:
            mark(root, 'short-caller-wait-timeout')
        else:
            raise AssertionError('short caller wait unexpectedly completed')
        notice = await_value(lambda: received[0] if received else None, seconds=6)
        before = task.observe()
        save(root / 'before-cancel.json', before)
        save(root / 'windows.json', task.stall_windows())
        try:
            cancellation = task.cancel_if_stalled(notice)
        except Exception as error:
            save(root / 'cancel-error.json', {'type': type(error).__name__, 'message': str(error),
                'sqlite_errorcode': getattr(error, 'sqlite_errorcode', None), 'traceback': traceback.format_exc()})
            try:
                save(root / 'uncommitted-cancel-observation.json', task.observe(timeout=.5))
            except Exception as observation_error:
                save(root / 'cancel-inspection-error.json', {'type': type(observation_error).__name__,
                                                           'message': str(observation_error)})
            raise
        save(root / 'cancel-receipt.json', cancellation.to_dict())
        result = task.wait(timeout=15)
        after = task.observe()
        save(root / 'caller-result.json', result)
        save(root / 'after-cancel.json', after)
        save(root / 'notifications.json', app.stall_notification_page())
        ticks = (root / 'descendant-ticks').stat().st_size
        time.sleep(.15)
        stable = (root / 'descendant-ticks').stat().st_size == ticks
        mark(root, 'descendant-stop-check', stable=stable, byte_count=ticks)
        check(before['execution']['state'] == 'running', 'caller wait cancelled execution')
        check(before['metrics']['stdout_bytes']['count'] == 0, 'silent stream invented output')
        check(before['output']['stdout']['first_missing'] is True, 'silent stream invented a first byte')
        check(result['status'] == 'cancelled', 'public conditional cancellation did not win')
        check(stable, 'descendant continued after cancellation')
        worker = next(item for item in after['processes'] if item['process_id'] == 'worker')
        check(worker['state'] == 'exited' and worker['evidence'].get('cleanup') == 'confirmed',
              'worker containment not confirmed')


@dataclass(frozen=True)
class LocalCleanupBackend:
    """Persistent local adapter fixture; subprocess execution is not mocked."""
    root: str
    name: str = 'sdk-a16-local-backend'
    revision: str = 'v1'

    def create(self, spec, *, operation_key, timeout):
        sandbox_id = uuid.uuid4().hex
        save(Path(self.root) / 'resource.json', {'sandbox_id': sandbox_id, 'operation_key': operation_key})
        return sandbox_id

    def find(self, operation_key, *, timeout):
        resource = read_json(Path(self.root) / 'resource.json')
        return (resource['sandbox_id'],) if resource and resource['operation_key'] == operation_key else ()

    def start(self, sandbox_id, spec, *, timeout):
        call(self.root, 'sandbox-start', sandbox_id=sandbox_id)
        if spec.interpreter != ('/fixture/python',) or spec.cwd != '/fixture':
            raise ValueError('local backend supports only its declared fixture interpreter and cwd')
        # SandboxSpec paths belong to the adapter namespace. Map that explicit
        # namespace to this real local interpreter/storage on either platform.
        source = Path(self.root) / 'uploaded-source.py'
        source.write_text(spec.source, encoding='utf-8')
        with (Path(self.root) / 'backend.stdout').open('wb') as output, \
             (Path(self.root) / 'backend.stderr').open('wb') as error:
            process = subprocess.Popen([sys.executable, str(source)], cwd=self.root,
                                       stdout=output, stderr=error)
            returncode = process.wait(timeout=timeout)
        save(Path(self.root) / 'command.json', {'pid': process.pid, 'returncode': returncode,
            'source': spec.source, 'sandbox_id': sandbox_id, 'received_spec': spec.to_payload(),
            'actual_interpreter': sys.executable, 'actual_cwd': self.root})
        return 'local-command'

    def inspect(self, sandbox_id, command_id, *, timeout):
        command = read_json(Path(self.root) / 'command.json')
        return SandboxObservation('succeeded' if command['returncode'] == 0 else 'failed',
                                  exit_code=command['returncode'])

    def collect(self, sandbox_id, command_id, spec, *, timeout):
        call(self.root, 'sandbox-collect', sandbox_id=sandbox_id)
        return {'stdout': (Path(self.root) / 'backend.stdout').read_text(),
                'stderr': (Path(self.root) / 'backend.stderr').read_text(), 'input_source': spec.source}

    def terminate(self, sandbox_id, *, timeout):
        if (Path(self.root) / 'reject-cleanup').exists():
            mark(self.root, 'cleanup-rejected', sandbox_id=sandbox_id, reason='injected local resource removal failure')
            return False
        (Path(self.root) / 'resource.json').unlink(missing_ok=True)
        mark(self.root, 'cleanup-confirmed', sandbox_id=sandbox_id)
        return True


def cleanup_phase(root, phase):
    root.mkdir(parents=True, exist_ok=True)
    handler = SandboxHandler(LocalCleanupBackend(str(root)), str(root / 'sandbox.sqlite3'),
                             operation_timeout=2, poll_interval=.05)
    app = Dispatcher(root / 'application.sqlite3', {handler.handler_id: handler}, isolation_mode='process',
                     observation_options=OPTIONS)
    mark(root, 'controller-' + phase)
    if phase == 'first':
        (root / 'reject-cleanup').touch()
        source = "import os; os.write(1,b'original cleanup body result')"
        spec = SandboxSpec('local-fixture', source, ('/fixture/python',), '/fixture')
        save(root / 'configuration.json', {'source': source, 'execution_timeout': 12, 'caller_timeout': 15,
            'operation_timeout': 2, 'cleanup_rejection': True})
        app.start()
        task = app.submit(handler.handler_id, spec.to_payload(), request_id='cleanup-once', timeout_seconds=12)
        try:
            task.wait(timeout=15)
        except RecoveryRequiredError as error:
            save(root / 'caller-recovery-error.json', {'type': type(error).__name__, 'message': str(error),
                                                     'snapshot': error.snapshot})
        else:
            raise AssertionError('cleanup failure was hidden')
        record = handler.journal().get(task.snapshot['command']['execution_id'])
        save(root / 'original-sandbox.json', record)
        save(root / 'first-observation.json', task.observe())
        try:
            app.close(timeout=8)
        except Exception as error:
            save(root / 'first-close-error.json', {'type': type(error).__name__, 'message': str(error)})
        check(record['result']['output']['stdout'] == 'original cleanup body result', 'collected result lost')
        check(not record['cleanup_confirmed'], 'failed cleanup reported confirmed')
        calls = [json.loads(line) for line in (root / 'calls.jsonl').read_text().splitlines()]
        check([item['phase'] for item in calls] == ['sandbox-start', 'sandbox-collect'],
              'cleanup fixture did not execute and collect exactly once')
        command = read_json(root / 'command.json')
        check(command['pid'] not in {os.getpid(), calls[0]['pid']} and calls[0]['pid'] != os.getpid(),
              'cleanup fixture did not cross real worker/tool processes')
    else:
        original = read_json(root / 'original-sandbox.json')
        original_calls = (root / 'calls.jsonl').read_text()
        (root / 'reject-cleanup').unlink()
        with app:
            task = app.task('cleanup-once')
            execution_id = task.snapshot['command']['execution_id']
            record = await_value(lambda: handler.journal().get(execution_id),
                                 lambda value: value['cleanup_confirmed'], seconds=6)
            save(root / 'recovered-sandbox.json', record)
            save(root / 'recovered-observation.json', task.observe())
            save(root / 'recovered-task.json', task.snapshot)
            check(record['result'] == original['result'], 'recovery changed original result')
            check(record['operation_key'] == original['operation_key'], 'recovery changed operation identity')
            check((root / 'calls.jsonl').read_text() == original_calls, 'recovery replayed business')
            check(task.state == 'recovery_required', 'cleanup silently resolved external effects')


def cleanup_restart_case(root):
    for phase in ('first', 'recover'):
        completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--evidence-dir', str(root),
            '--scenario', 'cleanup', '--phase', phase], capture_output=True, text=True, timeout=35)
        save(root / (phase + '-controller-result.json'), {'returncode': completed.returncode,
            'stdout': completed.stdout, 'stderr': completed.stderr})
        check(completed.returncode == 0, 'cleanup controller failed: ' + completed.stderr)
    check(read_json(root / 'controller-first.json')['pid'] != read_json(root / 'controller-recover.json')['pid'],
          'recovery did not cross controller lifetime')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir', type=Path)
    parser.add_argument('--scenario', choices=('all', 'success', 'failure', 'budget', 'silence', 'cleanup'), default='all')
    parser.add_argument('--phase', choices=('first', 'recover'))
    parser.add_argument('--fixture-tool', nargs=2, metavar=('DIRECTORY', 'PAYLOAD'))
    arguments = parser.parse_args()
    if arguments.fixture_tool:
        return local_tool(arguments.fixture_tool[0], json.loads(arguments.fixture_tool[1]))
    if arguments.evidence_dir is None:
        parser.error('--evidence-dir is required')
    root = arguments.evidence_dir.resolve()
    if arguments.phase != 'recover' and root.exists() and any(root.iterdir()):
        parser.error('--evidence-dir must be empty for a new invocation; preserve prior evidence in its own directory')
    if arguments.phase == 'recover' and not (root / 'original-sandbox.json').is_file():
        parser.error('cleanup recovery requires the original phase evidence')
    root.mkdir(parents=True, exist_ok=True)
    mark(root, 'environment' + ('-' + arguments.phase if arguments.phase else ''),
         platform=platform.platform(), machine=platform.machine(), scenario=arguments.scenario,
         distribution_version=version('dispatcher-sdk'))
    try:
        if arguments.phase:
            check(arguments.scenario == 'cleanup', '--phase applies only to cleanup')
            cleanup_phase(root, arguments.phase)
        else:
            cases = {
                'success': lambda location: parent_child_case(location, 'success'),
                'failure': lambda location: parent_child_case(location, 'failure'),
                'budget': lambda location: parent_child_case(location, 'blocked'),
                'silence': silence_cancel_case,
                'cleanup': cleanup_restart_case,
            }
            selected = tuple(cases) if arguments.scenario == 'all' else (arguments.scenario,)
            for name in selected:
                location = root / name
                location.mkdir(parents=True, exist_ok=True)
                try:
                    cases[name](location)
                except BaseException:
                    save(location / 'failure.json', {'traceback': traceback.format_exc()})
                    raise
                save(location / 'passed.json', {'scenario': name, 'passed': True})
            save(root / 'summary.json', {'passed': True, 'scenarios': list(selected)})
    except BaseException as error:
        save(root / 'failure.json', {'type': type(error).__name__, 'message': str(error),
                                   'traceback': traceback.format_exc()})
        raise
    print(json.dumps({'evidence_dir': str(root), 'passed': True, 'scenario': arguments.scenario}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
