import ast
import operator
from integrations.utils import (
    generate_pub_links,
    get_partner_tracker_identifiers,
    get_partner_name_by_account_name_in_tracker,
    extract_domain,
)

class SafeEvaluator:
    """
    Safely evaluates Python expressions using AST.
    Restricted to basic arithmetic, comparisons, logic, and specific functions.
    """
    
    ALLOWED_NODES = {
        ast.Expression, ast.Load,
        ast.Constant, ast.Name, 
        ast.UnaryOp, ast.BinOp, ast.BoolOp, ast.Compare,
        ast.Subscript, ast.Index, ast.Slice,  # For list/dict access
        ast.Call, ast.Attribute, # For method calls (restricted)
        ast.keyword,
        ast.ListComp, ast.comprehension, # For list comprehensions
        ast.List, ast.Dict, # For list/dict literals
        ast.IfExp, # For ternary conditional
    }
    
    ALLOWED_FUNCS = {
        'len': len,
        'int': int,
        'str': str,
        'float': float,
        'bool': bool,
        'list': list,
        'dict': dict,
        'abs': abs,
        'round': round,
        'find': lambda lst, k, v: next((x for x in lst if isinstance(x, dict) and x.get(k) == v), None),
        'sum': sum,
        'max': max,
        'min': min,

        'max': max,
        'min': min,

        'generate_pub_links': generate_pub_links,
        'get_partner_tracker_identifiers': get_partner_tracker_identifiers,
        'get_partner_name_by_account_name_in_tracker': get_partner_name_by_account_name_in_tracker,
        'extract_domain': extract_domain,
    }
    
    OPS = {
        # Math
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
        
        # Logic
        ast.And: lambda a, b: a and b, # Short-circuit handled in visit_BoolOp
        ast.Or: lambda a, b: a or b,
        ast.Not: operator.not_,
        
        # Comparison
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
        ast.Is: operator.is_,
        ast.IsNot: operator.is_not,
    }

    def __init__(self, context=None):
        self.context = context or {}
        # Add allowed functions to context
        self.context.update(self.ALLOWED_FUNCS)

    def evaluate(self, expression):
        if not expression or not expression.strip():
            return True # Empty condition is considered success
            
        try:
            tree = ast.parse(expression, mode='eval')
            return self._visit(tree.body)
        except Exception as e:
            raise ValueError(f"Evaluation error: {str(e)}")

    def _visit(self, node):
        if type(node) not in self.ALLOWED_NODES:
            raise ValueError(f"Unsafe or unsupported operation: {type(node).__name__}")
            
        if isinstance(node, ast.Expression):
            return self._visit(node.body)
            
        elif isinstance(node, ast.Constant):
            return node.value
            
        elif isinstance(node, ast.Name):
            if node.id in self.context:
                return self.context[node.id]
            raise ValueError(f"Unknown variable: {node.id}")

        elif isinstance(node, ast.List):
            return [self._visit(elt) for elt in node.elts]
            
        elif isinstance(node, ast.Dict):
            return {self._visit(k): self._visit(v) for k, v in zip(node.keys, node.values)}
            
        elif isinstance(node, ast.BinOp):
            left = self._visit(node.left)
            right = self._visit(node.right)
            op = self.OPS.get(type(node.op))
            if not op:
                raise ValueError(f"Unknown operator: {type(node.op).__name__}")
            return op(left, right)
            
        elif isinstance(node, ast.UnaryOp):
            operand = self._visit(node.operand)
            op = self.OPS.get(type(node.op))
            if not op:
                raise ValueError(f"Unknown operator: {type(node.op).__name__}")
            return op(operand)
            
        elif isinstance(node, ast.BoolOp):
            # Handle short-circuit logic
            values = [self._visit(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            elif isinstance(node.op, ast.Or):
                return any(values)
            
        elif isinstance(node, ast.Compare):
            left = self._visit(node.left)
            for op_node, comparator in zip(node.ops, node.comparators):
                right = self._visit(comparator)
                op = self.OPS.get(type(op_node))
                if not op:
                    raise ValueError(f"Unknown operator: {type(op_node).__name__}")
                if not op(left, right):
                    return False
                left = right
            return True
            
        elif isinstance(node, ast.Subscript):
            value = self._visit(node.value)
            # Handle Python < 3.9 Index wrapper
            if hasattr(ast, 'Index') and isinstance(node.slice, ast.Index):
                 slice_val = self._visit(node.slice.value)
            else:
                 slice_val = self._visit(node.slice)
            return value[slice_val]
            
        elif isinstance(node, ast.Call):
            func = self._visit(node.func)
            
            # Check ALLOWED_FUNCS OR Context-provided functions
            is_allowed = False
            if func in self.ALLOWED_FUNCS.values():
                is_allowed = True
            elif func in self.context.values() and callable(func):
                is_allowed = True
                
            if not is_allowed:
                 raise ValueError(f"Function call not allowed: {getattr(func, '__name__', str(func))}")
            
            args = [self._visit(arg) for arg in node.args]
            keywords = {kw.arg: self._visit(kw.value) for kw in node.keywords}
            return func(*args, **keywords)
            
        elif isinstance(node, ast.Attribute):
            # Allow accessing dict keys via .get? No, that's a method call.
            # Allow accessing properties?
            # For safety, let's only allow accessing attributes of objects provided in context
            # AND restrict what attributes can be accessed (no __class__, etc)
            value = self._visit(node.value)
            attr = node.attr
            if attr.startswith('_'):
                raise ValueError(f"Access to private attribute '{attr}' is denied.")
            
            # Support Dict Dot Notation
            if isinstance(value, dict):
                return value.get(attr)
                
            return getattr(value, attr)

        elif isinstance(node, ast.ListComp):
            # Support basic list comprehensions: [x.id for x in items if x.active]
            # Restriction: Only 1 generator/loop allowed
            if len(node.generators) != 1:
               raise ValueError("Only single-loop list comprehensions are supported")
               
            gen = node.generators[0]
            if not isinstance(gen.target, ast.Name):
               raise ValueError("List comprehension target must be a simple variable name")
               
            target_var = gen.target.id
            iterable = self._visit(gen.iter)
            
            # Save original context if variable name conflicts
            has_original = target_var in self.context
            original_val = self.context.get(target_var)
            
            result = []
            try:
                # We iterate over the actual list/iterable
                for item in iterable:
                    # Update context for the loop variable
                    self.context[target_var] = item
                    
                    # Evaluate If conditions (all must be true)
                    include = True
                    for if_node in gen.ifs:
                        if not self._visit(if_node):
                            include = False
                            break
                    
                    if include:
                        result.append(self._visit(node.elt))
            finally:
                # Restore original context
                if has_original:
                    self.context[target_var] = original_val
                elif target_var in self.context:
                    del self.context[target_var]
            
            return result
        
        elif isinstance(node, ast.IfExp):
            # Support ternary conditional: a if test else b
            if self._visit(node.test):
                return self._visit(node.body)
            else:
                return self._visit(node.orelse)

        raise ValueError(f"Unsupported node type: {type(node).__name__}")
