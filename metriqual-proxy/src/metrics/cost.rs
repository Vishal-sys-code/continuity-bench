use serde_json::Value;

pub fn calculate_cost(response: &Value, model: &str) -> f64 {
    // Basic cost tracking stub
    let usage = match response.get("usage") {
        Some(u) => u,
        None => return 0.0,
    };

    let prompt_tokens = usage.get("prompt_tokens").and_then(|v| v.as_f64()).unwrap_or(0.0);
    let completion_tokens = usage.get("completion_tokens").and_then(|v| v.as_f64()).unwrap_or(0.0);

    // Mock pricing table
    let (prompt_price, completion_price) = match model {
        "gpt-4o" => (0.005 / 1000.0, 0.015 / 1000.0),
        "claude-3-5-sonnet-20240620" => (0.003 / 1000.0, 0.015 / 1000.0),
        _ => (0.001 / 1000.0, 0.002 / 1000.0), // Default cheap model
    };

    let total_cost = (prompt_tokens * prompt_price) + (completion_tokens * completion_price);
    
    // In a real app, we'd log this to Prometheus/Redis here
    tracing::info!("Estimated cost for {}: ${:.6}", model, total_cost);

    total_cost
}
