"""Bounded decimal arithmetic; no eval, Python calls, names, powers or I/O."""
import ast,re
from decimal import Decimal,localcontext,DecimalException

def calculate(expression):
    if not isinstance(expression,str) or not 1<=len(expression)<=120:raise ValueError('expression_length')
    expression=expression.strip().replace(',','.')
    if not re.fullmatch(r'[0-9.\s()+*/-]+',expression):raise ValueError('unsupported_characters')
    if '**' in expression or '//' in expression:raise ValueError('unsupported_operator')
    depth=0
    for c in expression:
        depth+=int(c=='(')-int(c==')')
        if depth<0 or depth>8:raise ValueError('parenthesis_depth')
    if depth:raise ValueError('unbalanced_parentheses')
    if any(len(x.replace('.',''))>15 for x in re.findall(r'\d+(?:\.\d*)?',expression)):raise ValueError('number_length')
    try:tree=ast.parse(expression,mode='eval')
    except (SyntaxError,ValueError,RecursionError) as e:raise ValueError('invalid_expression') from e
    if sum(1 for _ in ast.walk(tree))>64:raise ValueError('too_many_nodes')
    def visit(node,level=0):
        if level>16:raise ValueError('expression_depth')
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            result=Decimal(ast.get_source_segment(expression,node))
            if abs(result)>Decimal('1e12'):raise ValueError('number_range')
        elif isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            result=visit(node.operand,level+1)*(1 if isinstance(node.op,ast.UAdd) else -1)
        elif isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
            a,b=visit(node.left,level+1),visit(node.right,level+1)
            if isinstance(node.op,ast.Add):result=a+b
            elif isinstance(node.op,ast.Sub):result=a-b
            elif isinstance(node.op,ast.Mult):result=a*b
            else:result=a/b
        else:raise ValueError('unsupported_syntax')
        if not result.is_finite() or abs(result)>Decimal('1e15'):raise ValueError('result_range')
        return result
    try:
        with localcontext() as ctx:ctx.prec=28;value=visit(tree.body)
    except DecimalException as e:raise ValueError('arithmetic_error') from e
    result=format(value,'f')
    if '.' in result:result=result.rstrip('0').rstrip('.')
    if result=='-0':result='0'
    return {'expression':expression,'value':result,'answer':f'{expression} = {result}','sources':[]}

def extract_expression(question):
    q=question.strip().rstrip('?.!')
    percent=re.fullmatch(r'(?:сколько(?:\s+будет)?|посчитай|вычисли)\s+(\d+(?:[.,]\d+)?)\s*%\s*от\s*(\d+(?:[.,]\d+)?)',q,re.I)
    if percent:return f'({percent[1]})*({percent[2]})/100'
    q=re.sub(r'^(?:посчитай|вычисли|рассчитай|сколько(?:\s+будет)?)\s*:?\s*','',q,flags=re.I)
    return q if re.fullmatch(r'[0-9.,\s()+*/-]+',q) and re.search(r'\d',q) else None
