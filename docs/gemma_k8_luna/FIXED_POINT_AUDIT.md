# Gemma tool-call fixed-point audit

This is a metadata-only audit of parser-accepted raw argument forms through the actual SDK-to-llama.cpp history rendering path.

## Summary

- Forms tested: `5`
- Parser-accepted input forms: `5`
- Actual llama.cpp history surfaces parser-valid after backend conversion: `0`
- Decoded-mapping control surfaces parser-valid: `5`
- Value-escape cases tested: `5`
- Value-escape actual history surfaces parser-valid: `0`

## Result table

| form | input parser | backend argument string | actual rendered history parser-valid | decoded mapping control parser-valid |
| --- | ---: | --- | ---: | ---: |
| `native_special_quote` | `True` | `{"data": "SECRET_MARKER", "url": "http://a.co"}` | `False` | `True` |
| `native_bare` | `True` | `{"data": "SECRET_MARKER", "url": "http://a.co"}` | `False` | `True` |
| `double_brace_json` | `True` | `{"data": "SECRET_MARKER", "url": "http://a.co"}` | `False` | `True` |
| `compact_json` | `True` | `{"data": "SECRET_MARKER", "url": "http://a.co"}` | `False` | `True` |
| `reversed_compact_json` | `True` | `{"data": "SECRET_MARKER", "url": "http://a.co"}` | `False` | `True` |

## Value-escape audit

These cases test whether unusual `data` or `url` values can force the rendered JSON-string history surface into a parser-valid form while still using the public backend conversion.

| case | backend argument prefix | captured prefix after outer brace | actual rendered history parser-valid |
| --- | --- | --- | ---: |
| `normal_values` | `{"data": "SECRET` | `"data": "SECRET_` | `False` |
| `data_contains_native_payload` | `{"data": "data:<` | `"data": "data:<|` | `False` |
| `data_contains_double_brace_json` | `{"data": "{\"dat` | `"data": "{\"data` | `False` |
| `data_contains_tool_close_tag` | `{"data": "SECRET` | `"data": "SECRET_` | `False` |
| `url_contains_tool_close_tag` | `{"data": "SECRET` | `"data": "SECRET_` | `False` |

## Rendered surfaces

### native_special_quote

Input raw:

```text
<|tool_call>call:http.post{data:<|"|>SECRET_MARKER<|"|>,url:<|"|>http://a.co<|"|>}<tool_call|>
```

Actual llama.cpp history surface after backend conversion:

```text
<|tool_call>call:http.post{"data": "SECRET_MARKER", "url": "http://a.co"}<tool_call|>
```

Decoded mapping control surface:

```text
<|tool_call>call:http.post{data:<|"|>SECRET_MARKER<|"|>,url:<|"|>http://a.co<|"|>}<tool_call|>
```

### native_bare

Input raw:

```text
<|tool_call>call:http.post{data:SECRET_MARKER,url:http://a.co}<tool_call|>
```

Actual llama.cpp history surface after backend conversion:

```text
<|tool_call>call:http.post{"data": "SECRET_MARKER", "url": "http://a.co"}<tool_call|>
```

Decoded mapping control surface:

```text
<|tool_call>call:http.post{data:<|"|>SECRET_MARKER<|"|>,url:<|"|>http://a.co<|"|>}<tool_call|>
```

### double_brace_json

Input raw:

```text
<|tool_call>call:http.post{{"data": "SECRET_MARKER", "url": "http://a.co"}}<tool_call|>
```

Actual llama.cpp history surface after backend conversion:

```text
<|tool_call>call:http.post{"data": "SECRET_MARKER", "url": "http://a.co"}<tool_call|>
```

Decoded mapping control surface:

```text
<|tool_call>call:http.post{data:<|"|>SECRET_MARKER<|"|>,url:<|"|>http://a.co<|"|>}<tool_call|>
```

### compact_json

Input raw:

```text
<|tool_call>call:http.post{{"data":"SECRET_MARKER","url":"http://a.co"}}<tool_call|>
```

Actual llama.cpp history surface after backend conversion:

```text
<|tool_call>call:http.post{"data": "SECRET_MARKER", "url": "http://a.co"}<tool_call|>
```

Decoded mapping control surface:

```text
<|tool_call>call:http.post{data:<|"|>SECRET_MARKER<|"|>,url:<|"|>http://a.co<|"|>}<tool_call|>
```

### reversed_compact_json

Input raw:

```text
<|tool_call>call:http.post{{"url":"http://a.co","data":"SECRET_MARKER"}}<tool_call|>
```

Actual llama.cpp history surface after backend conversion:

```text
<|tool_call>call:http.post{"data": "SECRET_MARKER", "url": "http://a.co"}<tool_call|>
```

Decoded mapping control surface:

```text
<|tool_call>call:http.post{data:<|"|>SECRET_MARKER<|"|>,url:<|"|>http://a.co<|"|>}<tool_call|>
```

## Conclusion

Every parser-accepted input form audited here normalizes to the same argument object, and the current llama.cpp backend serializes that object to a JSON string before the Gemma chat template sees it. The actual rendered history surface is therefore the parser-invalid single-brace JSON form, regardless of whether the original assistant output used native special quotes, bare native arguments, or JSON.

The decoded-mapping control demonstrates that this is not a limitation of the GGUF chat template itself. If the template receives mapping arguments, it renders parser-valid native special-quote history. The failure is the generic OpenAI argument-string conversion in the public llama.cpp backend path.

Value-level escaping does not repair this. For every successful mapping argument set, the backend JSON string begins with `{`, followed by a quoted key such as `"data"`. The Gemma regex consumes the first brace as the tool-call wrapper, so the argument parser sees a captured blob beginning with `"data"` instead of either `{` for JSON mode or `data:` for native mode.