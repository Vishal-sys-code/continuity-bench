use regex::Regex;
use serde_json::Value;

pub fn redact_pii(mut payload: Value) -> Value {
    let email_regex = Regex::new(r"(?i)[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}").unwrap();
    
    if let Some(messages) = payload.get_mut("messages").and_then(|m| m.as_array_mut()) {
        for message in messages.iter_mut() {
            if let Some(content) = message.get_mut("content").and_then(|c| c.as_str()) {
                let redacted = email_regex.replace_all(content, "[REDACTED_EMAIL]");
                *message.get_mut("content").unwrap() = Value::String(redacted.into_owned());
            }
        }
    }
    
    payload
}
