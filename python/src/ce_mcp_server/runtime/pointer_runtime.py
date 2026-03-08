from __future__ import annotations

from ..context import RuntimeModule

POINTER_RUNTIME = RuntimeModule(
    name="pointer",
    version="2026.03.07.1",
    script=r'''
_G.__ce_mcp = _G.__ce_mcp or {}
_G.__ce_mcp_modules = _G.__ce_mcp_modules or {}
local root = _G.__ce_mcp
root.pointer = root.pointer or {}
local M = root.pointer

local function resolve_chain(base_address, offsets)
  local current = getAddressSafe(base_address)
  if current == nil then
    error('pointer_base_not_found')
  end

  offsets = offsets or {}
  if #offsets == 0 then
    return current
  end

  for index, offset in ipairs(offsets) do
    if index < #offsets then
      current = readPointer(current + offset)
      if current == nil then
        error('pointer_dereference_failed')
      end
    else
      current = current + offset
    end
  end

  return current
end

local READERS = {
  byte = function(address) return readBytes(address, 1, true)[1] end,
  bytes = function(address, size) return readBytes(address, size, true) end,
  small_integer = function(address) return readSmallInteger(address) end,
  integer = function(address) return readInteger(address) end,
  qword = function(address) return readQword(address) end,
  pointer = function(address) return readPointer(address) end,
  float = function(address) return readFloat(address) end,
  double = function(address) return readDouble(address) end,
  string = function(address, max_length, wide) return readString(address, max_length, wide) end,
}

local WRITERS = {
  byte = function(address, value) return writeBytes(address, value) end,
  bytes = function(address, values) return writeBytes(address, values) end,
  small_integer = function(address, value) return writeSmallInteger(address, value) end,
  integer = function(address, value) return writeInteger(address, value) end,
  qword = function(address, value) return writeQword(address, value) end,
  pointer = function(address, value) return writePointer(address, value) end,
  float = function(address, value) return writeFloat(address, value) end,
  double = function(address, value) return writeDouble(address, value) end,
  string = function(address, value) return writeString(address, value) end,
}

function M.resolve(base_address, offsets)
  local address = resolve_chain(base_address, offsets)
  return {address = address, address_hex = string.format('0x%X', address)}
end

function M.read(kind, base_address, offsets, size_or_length, wide)
  local address = resolve_chain(base_address, offsets)
  local reader = READERS[kind]
  if reader == nil then
    error('unsupported_pointer_read_kind:' .. tostring(kind))
  end

  local value
  if kind == 'bytes' then
    value = reader(address, size_or_length or 1)
  elseif kind == 'string' then
    value = reader(address, size_or_length or 32, wide and true or false)
  else
    value = reader(address)
  end

  return {address = address, kind = kind, value = value}
end

function M.write(kind, base_address, offsets, value)
  local address = resolve_chain(base_address, offsets)
  local writer = WRITERS[kind]
  if writer == nil then
    error('unsupported_pointer_write_kind:' .. tostring(kind))
  end

  local ok = writer(address, value)
  return {address = address, kind = kind, value = value, success = ok and true or false}
end

_G.__ce_mcp_modules["pointer"] = "2026.03.07.1"
return {ok = true, module = "pointer", version = "2026.03.07.1"}
''',
)
