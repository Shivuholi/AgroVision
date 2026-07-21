// Global Chart defaults for dark theme
Chart.defaults.color = '#94a3b8';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(15, 23, 42, 0.9)';
Chart.defaults.plugins.tooltip.titleColor = '#f8fafc';
Chart.defaults.plugins.tooltip.bodyColor = '#f8fafc';
Chart.defaults.plugins.tooltip.borderColor = 'rgba(255,255,255,0.1)';
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.scale.grid.color = 'rgba(255, 255, 255, 0.05)';

let envChartInstance = null;
let soilChartInstance = null;

function initCharts() {
    const ctxEnv = document.getElementById('envChart').getContext('2d');
    const ctxSoil = document.getElementById('soilChart').getContext('2d');

    envChartInstance = new Chart(ctxEnv, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Temperature (°C)',
                    data: [],
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    yAxisID: 'y'
                },
                {
                    label: 'Humidity (%)',
                    data: [],
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: { display: true },
                y: { type: 'linear', display: true, position: 'left' },
                y1: { type: 'linear', display: true, position: 'right', grid: { drawOnChartArea: false } }
            }
        }
    });

    soilChartInstance = new Chart(ctxSoil, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Soil Moisture (%)',
                    data: [],
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { display: true },
                y: { display: true, min: 0, max: 100 }
            }
        }
    });
}

function updateCharts(historyData) {
    if (!envChartInstance || !soilChartInstance) return;

    // historyData comes sorted from oldest to newest (we reversed it in backend)
    const labels = historyData.map(d => {
        const date = new Date(d.timestamp);
        return `${date.getHours().toString().padStart(2,'0')}:${date.getMinutes().toString().padStart(2,'0')}`;
    });
    
    const temps = historyData.map(d => d.temperature);
    const hums = historyData.map(d => d.humidity);
    const soils = historyData.map(d => d.soil_moisture);

    envChartInstance.data.labels = labels;
    envChartInstance.data.datasets[0].data = temps;
    envChartInstance.data.datasets[1].data = hums;
    envChartInstance.update('none'); // Update without animation for smooth polling

    soilChartInstance.data.labels = labels;
    soilChartInstance.data.datasets[0].data = soils;
    soilChartInstance.update('none');
}

// Export functions to global scope
window.initCharts = initCharts;
window.updateCharts = updateCharts;
