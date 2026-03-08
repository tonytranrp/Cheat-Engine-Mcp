#include "core_runtime_internal.hpp"

#include <iomanip>
#include <sstream>

namespace
{
struct ExportedFieldDescriptor
{
    const char* name;
    const char* type_name;
    const char* kind;
    bool callable;
    std::size_t offset;
    std::size_t size;
};

const ExportedFieldDescriptor* find_exported_field(std::string_view name)
{
    static const ExportedFieldDescriptor fields[] = {
#define CE_MCP_EXPORTED_FIELD(name, type_name, kind_name, callable_flag) \
        {#name, type_name, kind_name, callable_flag, offsetof(ExportedFunctions, name), sizeof(((ExportedFunctions*)nullptr)->name)},
#include "exported_field_catalog.inc"
#undef CE_MCP_EXPORTED_FIELD
    };

    for (const auto& field : fields)
    {
        if (ce_mcp::equals_case_insensitive(field.name, name))
        {
            return &field;
        }
    }

    return nullptr;
}

const ExportedFieldDescriptor* exported_fields_begin()
{
    static const ExportedFieldDescriptor fields[] = {
#define CE_MCP_EXPORTED_FIELD(name, type_name, kind_name, callable_flag) \
        {#name, type_name, kind_name, callable_flag, offsetof(ExportedFunctions, name), sizeof(((ExportedFunctions*)nullptr)->name)},
#include "exported_field_catalog.inc"
#undef CE_MCP_EXPORTED_FIELD
    };
    return fields;
}

std::size_t exported_fields_count()
{
    static const std::size_t count = []()
    {
        std::size_t value = 0;
#define CE_MCP_EXPORTED_FIELD(name, type_name, kind_name, callable_flag) ++value;
#include "exported_field_catalog.inc"
#undef CE_MCP_EXPORTED_FIELD
        return value;
    }();
    return count;
}

std::string pointer_to_hex(std::uintptr_t value)
{
    std::ostringstream stream;
    stream << "0x" << std::hex << std::uppercase << value;
    return stream.str();
}

bool field_within_exported_block(PExportedFunctions exported, const ExportedFieldDescriptor& field)
{
    if (exported == nullptr || exported->sizeofExportedFunctions <= 0)
    {
        return false;
    }

    const auto block_size = static_cast<std::size_t>(exported->sizeofExportedFunctions);
    return field.offset + field.size <= block_size;
}

bool try_read_exported_pointer_value(PExportedFunctions exported,
                                     const ExportedFieldDescriptor& field,
                                     std::uintptr_t& value)
{
    if (exported == nullptr || !field_within_exported_block(exported, field))
    {
        return false;
    }

    __try
    {
        value = 0;
        const auto* bytes = reinterpret_cast<const unsigned char*>(exported) + field.offset;
        std::memcpy(&value, bytes, (std::min)(sizeof(value), field.size));
        return true;
    }
    __except (EXCEPTION_EXECUTE_HANDLER)
    {
        return false;
    }
}

bool try_read_exported_size_value(PExportedFunctions exported, int& value)
{
    if (exported == nullptr)
    {
        return false;
    }

    __try
    {
        value = exported->sizeofExportedFunctions;
        return true;
    }
    __except (EXCEPTION_EXECUTE_HANDLER)
    {
        return false;
    }
}

void append_exported_field_json_body(std::ostringstream& stream,
                                     PExportedFunctions exported,
                                     const ExportedFieldDescriptor& field)
{
    stream << "\"name\":\"" << ce_mcp::escape_json_string(field.name) << "\""
           << ",\"type_name\":\"" << ce_mcp::escape_json_string(field.type_name) << "\""
           << ",\"kind\":\"" << ce_mcp::escape_json_string(field.kind) << "\""
           << ",\"callable\":" << (field.callable ? "true" : "false")
           << ",\"offset\":" << field.offset
           << ",\"size\":" << field.size
           << ",\"in_exported_block\":" << (field_within_exported_block(exported, field) ? "true" : "false");

    if (std::string_view(field.kind) == "size")
    {
        int size_value = 0;
        const bool ok = try_read_exported_size_value(exported, size_value);
        stream << ",\"available\":" << (ok ? "true" : "false")
               << ",\"value\":" << size_value;
    }
    else
    {
        std::uintptr_t pointer_value = 0;
        const bool ok = try_read_exported_pointer_value(exported, field, pointer_value);
        stream << ",\"available\":" << ((ok && pointer_value != 0) ? "true" : "false")
               << ",\"address\":" << pointer_value
               << ",\"address_hex\":\"" << pointer_to_hex(pointer_value) << "\"";
    }

}

void append_exported_field_json(std::ostringstream& stream,
                                PExportedFunctions exported,
                                const ExportedFieldDescriptor& field)
{
    stream << "{";
    append_exported_field_json_body(stream, exported, field);
    stream << "}";
}
}

namespace ce_mcp
{
std::string CoreRuntime::Impl::make_exported_list_response(std::string_view request_id, std::string_view line) const
{
    if (exported_ == nullptr)
    {
        return make_error_response(request_id, "missing_exported_functions");
    }

    bool available_only = false;
    if (const auto text = extract_simple_field(line, "available_only"))
    {
        if (!parse_bool(*text, available_only))
        {
            return make_error_response(request_id, "invalid_available_only");
        }
    }

    std::size_t limit = exported_fields_count();
    if (const auto text = extract_simple_field(line, "limit"))
    {
        const auto parsed = parse_unsigned_integer(*text);
        if (!parsed || *parsed == 0 || *parsed > exported_fields_count())
        {
            return make_error_response(request_id, "invalid_limit");
        }

        limit = static_cast<std::size_t>(*parsed);
    }

    const auto* fields = exported_fields_begin();
    const auto count = exported_fields_count();

    std::size_t returned_count = 0;
    std::size_t available_count = 0;
    std::ostringstream stream;
    stream << "{\"type\":\"result\",\"id\":" << quote_json_or_literal(request_id)
           << ",\"ok\":true,\"result\":{"
           << "\"total_count\":" << count
           << ",\"fields\":[";

    bool first = true;
    for (std::size_t index = 0; index < count; ++index)
    {
        const auto& field = fields[index];
        std::uintptr_t pointer_value = 0;
        int size_value = 0;
        const bool is_size = std::string_view(field.kind) == "size";
        const bool present = is_size ? try_read_exported_size_value(exported_, size_value)
                                     : try_read_exported_pointer_value(exported_, field, pointer_value);
        const bool available = is_size ? present : (present && pointer_value != 0);
        if (available)
        {
            ++available_count;
        }

        if (available_only && !available)
        {
            continue;
        }

        if (returned_count >= limit)
        {
            break;
        }

        if (!first)
        {
            stream << ",";
        }
        append_exported_field_json(stream, exported_, field);
        first = false;
        ++returned_count;
    }

    stream << "]"
           << ",\"returned_count\":" << returned_count
           << ",\"available_count\":" << available_count
           << ",\"sizeof_exported_functions\":" << exported_->sizeofExportedFunctions
           << "}}";
    return stream.str();
}

std::string CoreRuntime::Impl::make_exported_get_response(std::string_view request_id, std::string_view line) const
{
    if (exported_ == nullptr)
    {
        return make_error_response(request_id, "missing_exported_functions");
    }

    const auto field_name = extract_string_field(line, "field_name");
    if (!field_name)
    {
        return make_error_response(request_id, "missing_field_name");
    }

    const auto* field = find_exported_field(*field_name);
    if (field == nullptr)
    {
        return make_error_response(request_id, "exported_field_not_found");
    }

    std::ostringstream stream;
    stream << "{\"type\":\"result\",\"id\":" << quote_json_or_literal(request_id)
           << ",\"ok\":true,\"result\":{";
    append_exported_field_json_body(stream, exported_, *field);
    stream << ",\"sizeof_exported_functions\":" << exported_->sizeofExportedFunctions << "}}";
    return stream.str();
}
}
