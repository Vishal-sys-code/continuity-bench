use axum::{
    http::{HeaderMap, StatusCode},
    Json,
};
use reqwest::Client;
use serde_json::Value;
use crate::middleware::pii::redact_pii;
use crate::metrics::cost::calculate_cost;

pub async fn handle_chat_completion(
    headers: HeaderMap,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let client = Client::new();
    
    // 1. Middleware: Redact PII
    let clean_payload = redact_pii(payload);
    
    let model = clean_payload
        .get("model")
        .and_then(|m| m.as_str())
        .unwrap_or("unknown");

    // Retrieve API key from headers (or env in a real app)
    let auth_header = headers.get("authorization")
        .and_then(|h| h.to_str().ok())
        .unwrap_or("");

    // 2. Routing Logic (Failover implementation)
    // Primary: OpenAI
    tracing::info!("Routing request to primary provider (OpenAI) for model: {}", model);
    let mut response = client
        .post("https://api.openai.com/v1/chat/completions")
        .header("Authorization", auth_header)
        .header("Content-Type", "application/json")
        .json(&clean_payload)
        .send()
        .await;

    // Simulate Failover Check
    if let Ok(ref res) = response {
        if res.status() == 429 || res.status().is_server_error() {
            tracing::warn!("Primary provider failed with {}. Triggering failover...", res.status());
            
            // Fallback: Anthropic (Mocked rewrite for demonstration)
            tracing::info!("Routing request to fallback provider (Anthropic)");
            // In a real app, rewrite the `clean_payload` to Anthropic's schema.
            // For now, we'll just resend it (this would fail in reality if not rewritten).
            response = client
                .post("https://api.anthropic.com/v1/messages")
                .header("x-api-key", "dummy-anthropic-key")
                .header("anthropic-version", "2023-06-01")
                .header("Content-Type", "application/json")
                .json(&clean_payload) // Needs real translation
                .send()
                .await;
        }
    }

    match response {
        Ok(res) => {
            let status = res.status();
            let json_res: Value = res.json().await.unwrap_or(Value::Null);
            
            if status.is_success() {
                // 3. Metrics: Cost calculation
                calculate_cost(&json_res, model);
                Ok(Json(json_res))
            } else {
                Err((
                    StatusCode::from_u16(status.as_u16()).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR),
                    json_res.to_string(),
                ))
            }
        },
        Err(e) => Err((StatusCode::INTERNAL_SERVER_ERROR, e.to_string())),
    }
}
