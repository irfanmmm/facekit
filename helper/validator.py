from marshmallow import Schema, fields, validate

class BranchScheema(Schema):
    def __init__(self, *, only = None, exclude = ..., many = None, load_only = ..., dump_only = ..., partial = None, unknown = None):
        super().__init__(only=only, exclude=exclude, many=many, load_only=load_only, dump_only=dump_only, partial=partial, unknown=unknown)
        
    branch_name = fields.String(required=True)
    latitude = fields.String(  required=True)
    longitude = fields.String(required=True)
