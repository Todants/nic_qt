# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: messages.proto
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x0emessages.proto\x12\x11TestTask.Messages\"h\n\x07Request\x12\x16\n\x0ereturn_address\x18\x01 \x02(\t\x12\x12\n\nrequest_id\x18\x02 \x02(\t\x12 \n\x18proccess_time_in_seconds\x18\x03 \x01(\x02\x12\x0f\n\x07request\x18\x04 \x02(\x05\"0\n\x08Response\x12\x12\n\nrequest_id\x18\x01 \x02(\t\x12\x10\n\x08response\x18\x02 \x02(\x05')



_REQUEST = DESCRIPTOR.message_types_by_name['Request']
_RESPONSE = DESCRIPTOR.message_types_by_name['Response']
Request = _reflection.GeneratedProtocolMessageType('Request', (_message.Message,), {
  'DESCRIPTOR' : _REQUEST,
  '__module__' : 'messages_pb2'
  # @@protoc_insertion_point(class_scope:TestTask.Messages.Request)
  })
_sym_db.RegisterMessage(Request)

Response = _reflection.GeneratedProtocolMessageType('Response', (_message.Message,), {
  'DESCRIPTOR' : _RESPONSE,
  '__module__' : 'messages_pb2'
  # @@protoc_insertion_point(class_scope:TestTask.Messages.Response)
  })
_sym_db.RegisterMessage(Response)

if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  _REQUEST._serialized_start=37
  _REQUEST._serialized_end=141
  _RESPONSE._serialized_start=143
  _RESPONSE._serialized_end=191
# @@protoc_insertion_point(module_scope)
