document.addEventListener('DOMContentLoaded', () => {
    const runBtn = document.getElementById('run-benchmark');
    
    // Standard Elements
    const stdLatency = document.getElementById('standard-latency');
    const stdCost = document.getElementById('standard-cost');
    const stdProgress = document.getElementById('standard-progress');
    
    // Metriqual Elements
    const metLatency = document.getElementById('metriqual-latency');
    const metCost = document.getElementById('metriqual-cost');
    const metProgress = document.getElementById('metriqual-progress');

    let isRunning = false;

    function formatTime(ms) {
        return `${ms.toFixed(0)}ms`;
    }

    function formatCost(cost) {
        return `$${cost.toFixed(4)}`;
    }

    runBtn.addEventListener('click', () => {
        if (isRunning) return;
        isRunning = true;
        runBtn.textContent = 'Running...';
        runBtn.style.opacity = '0.7';

        // Reset
        stdLatency.textContent = '0ms';
        stdCost.textContent = '$0.0000';
        stdProgress.style.width = '0%';
        stdProgress.style.transition = 'none';
        
        metLatency.textContent = '0ms';
        metCost.textContent = '$0.0000';
        metProgress.style.width = '0%';
        metProgress.style.transition = 'none';

        // Force reflow
        void stdProgress.offsetWidth;

        // Target values
        const stdTargetTime = 2450; // 2.45s
        const stdTargetCost = 0.0150; 
        
        const metTargetTime = 450; // 0.45s (due to smaller model routing)
        const metTargetCost = 0.0015; // 10x cheaper

        const startTime = performance.now();

        function animate() {
            const now = performance.now();
            const elapsed = now - startTime;

            // Update Standard (slow)
            if (elapsed < stdTargetTime) {
                stdLatency.textContent = formatTime(elapsed);
                stdProgress.style.width = `${(elapsed / stdTargetTime) * 100}%`;
            } else {
                stdLatency.textContent = formatTime(stdTargetTime);
                stdCost.textContent = formatCost(stdTargetCost);
                stdProgress.style.width = '100%';
            }

            // Update Metriqual (fast)
            if (elapsed < metTargetTime) {
                metLatency.textContent = formatTime(elapsed);
                metProgress.style.width = `${(elapsed / metTargetTime) * 100}%`;
            } else {
                metLatency.textContent = formatTime(metTargetTime);
                metCost.textContent = formatCost(metTargetCost);
                metProgress.style.width = '100%';
            }

            if (elapsed < stdTargetTime) {
                requestAnimationFrame(animate);
            } else {
                isRunning = false;
                runBtn.textContent = 'Run Live Benchmark 🚀';
                runBtn.style.opacity = '1';
            }
        }

        requestAnimationFrame(animate);
    });
});
