use axum::{
    routing::post,
    Router,
};
use tracing_subscriber;

mod gateway;
mod middleware;
mod metrics;

#[tokio::main]
async fn main() {
    // Initialize structured logging
    tracing_subscriber::fmt::init();
    tracing::info!("Starting Metriqual Edge Proxy on 0.0.0.0:3000");

    let app = Router::new()
        .route("/v1/chat/completions", post(gateway::router::handle_chat_completion));

    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000").await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
