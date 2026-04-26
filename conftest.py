import sys, os, importlib.abc

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

class _TsAliasFinder(importlib.abc.MetaPathFinder):
    PREFIX = 'ts2i_ivs.'

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(self.PREFIX):
            return None
        flat = fullname[len(self.PREFIX):]
        # تحميل الـ flat module أولاً
        try:
            import importlib
            if flat not in sys.modules:
                mod = importlib.import_module(flat)
                sys.modules[flat] = mod
            # تسجيل نفس الـ object في المسارين
            sys.modules[fullname] = sys.modules[flat]
        except ImportError:
            pass
        return None

import types
pkg = types.ModuleType('ts2i_ivs')
pkg.__path__    = [project_root]
pkg.__package__ = 'ts2i_ivs'
sys.modules['ts2i_ivs'] = pkg

sys.meta_path.insert(0, _TsAliasFinder())
