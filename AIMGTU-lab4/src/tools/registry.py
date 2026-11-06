from src.tools.calculator import calculate
from src.security.policy import PolicyError

class Registry:
    """Finite dispatch, exact argument keys and at most one call per request."""
    SCHEMAS={'calculate':{'expression':str},'get_contact_information':{'department_id':str},
             'find_department':{'department_id':str},'search_knowledge_base':{'question':str}}
    def __init__(self,directory,rag):self.directory=directory;self.rag=rag;self.calls=[]
    def execute(self,name,args):
        if self.calls:raise PolicyError('tool_call_budget')
        if name not in self.SCHEMAS:raise PolicyError('unknown_tool')
        schema=self.SCHEMAS[name]
        if type(args) is not dict or set(args)!=set(schema):raise PolicyError('invalid_tool_arguments')
        if any(type(args[k]) is not t or not args[k] or len(args[k])>1500 for k,t in schema.items()):raise PolicyError('invalid_tool_arguments')
        self.calls.append({'tool':name,'arguments':dict(args)})
        if name=='calculate':return calculate(**args)
        if name=='find_department':return self.directory.find_department(**args)
        if name=='get_contact_information':return self.directory.get_contact_information(**args)
        return self.rag.ask(**args)
