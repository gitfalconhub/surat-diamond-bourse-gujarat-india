"""Exercise actual guard functions without running a Blender build or render."""
import ast
import tempfile
from pathlib import Path
from types import SimpleNamespace

root = Path(__file__).resolve().parents[1] / 'scripts'
tree = ast.parse((root/'build_sdb.py').read_text())
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('output_path','save','main')]
calls = []
fake = SimpleNamespace(data=SimpleNamespace(filepath='',is_dirty=False), ops=SimpleNamespace(wm=SimpleNamespace(
    save_as_mainfile=lambda **kw:calls.append(kw))))
ns = {'Path':Path,'bpy':fake,'JOB':{},'_WRITTEN_THIS_RUN':set(), 'status':lambda *a,**k:None}
exec(compile(ast.Module(body=functions,type_ignores=[]),'build_sdb.py','exec'),ns)
passed = []
def rejects(label, function, error):
    before = len(calls)
    try:
        function()
    except error:
        assert len(calls) == before
        passed.append(label)
    else:
        raise AssertionError('Guard did not reject ' + label)

with tempfile.TemporaryDirectory() as folder:
    project = Path(folder).resolve()/'project'
    project.mkdir()
    ns['PROJECT'] = project
    for name in ('../outside.blend','/private/tmp/outside.blend','wrong.txt'):
        rejects('unsafe save: '+name,lambda name=name:ns['save'](name),ValueError)
    outside = Path(folder).resolve()/'outside'
    outside.mkdir()
    (project/'linked').symlink_to(outside,target_is_directory=True)
    rejects('symlink escape',lambda:ns['save']('linked/output.blend'),ValueError)
    existing = project/'existing.blend'
    existing.write_bytes(b'preserve')
    rejects('existing output overwrite',lambda:ns['save']('existing.blend'),FileExistsError)
    assert existing.read_bytes() == b'preserve'
    ns['save']('checkpoints/new.blend')
    assert calls[-1]['filepath'] == str(project/'checkpoints/new.blend')
    passed.append('new checkpoint directory and bounded output')
    fake.data.filepath = str(existing)
    rejects('loaded scene reset',lambda:ns['main'](),RuntimeError)
    fake.data.filepath = ''
    fake.data.is_dirty = True
    rejects('unsaved edited scene reset',lambda:ns['main'](),RuntimeError)
    fake.data.is_dirty = False
    ns['JOB'] = {'phase':'full'}
    main = project/'Surat Diamond Bourse.blend'
    main.write_bytes(b'preserve main')
    rejects('authoritative model overwrite preflight',lambda:ns['main'](),FileExistsError)
    main.unlink()
    for prefix in ('../out_','path/out_','path\\out_'):
        ns['JOB']={'prefix':prefix}
        rejects('render path prefix: '+prefix,lambda:ns['main'](),ValueError)
    ns['JOB']={'save':'../outside.blend'}
    rejects('save traversal preflight before scene reset',lambda:ns['main'](),ValueError)
    showcase_tree = ast.parse((root/'build_showcase.py').read_text())
    fn = next(n for n in showcase_tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_showcase')
    movie = project/'video/Surat Diamond Bourse - Showcase.blend'
    other = {'Path':Path,'bpy':fake,'main':main,'VIDEO':movie.parent}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'build_showcase.py','exec'),other)
    rejects('wrong input showcase scene',lambda:other['build_showcase'](),RuntimeError)
    fake.data.filepath = str(main)
    movie.parent.mkdir()
    movie.write_bytes(b'preserve showcase')
    rejects('existing showcase overwrite',lambda:other['build_showcase'](),FileExistsError)
    assert movie.read_bytes() == b'preserve showcase'

for filename in ('build_sdb.py','build_showcase.py','fix_showcase_ramp.py'):
    module = ast.parse((root/filename).read_text())
    assert any(isinstance(n,ast.If) and '__name__' in ast.unparse(n.test) for n in module.body)
    passed.append('explicit execution guard: '+filename)
for file in root.glob('*.py'):
    compile(file.read_text(),str(file),'exec')
print('PASS',len(passed),'safety checks; twelve source modules compile')
