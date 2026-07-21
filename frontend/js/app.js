const API_BASE_URL = 'http://localhost:8000/api';

document.addEventListener('DOMContentLoaded', () => {
    // Initialize charts from charts.js
    if (window.initCharts) {
        window.initCharts();
    }

    // Start polling loop
    fetchData();
    fetchNutrients(); // Fetch manual nutrients initially
    fetchWeatherForecast(); // Fetch 24-hour forecast
    setInterval(fetchData, 5000); // Poll every 5 seconds
    setInterval(fetchWeatherForecast, 3600000); // Poll weather once an hour

    // Setup manual NPK form
    const npkForm = document.getElementById('npk-form');
    if (npkForm) {
        npkForm.addEventListener('submit', handleNpkSubmit);
    }

    // Modal setup
    const modal = document.getElementById('et-modal');
    const infoBtn = document.getElementById('et-info-btn');
    const closeBtn = document.getElementById('close-modal');

    infoBtn.onclick = function() {
        modal.style.display = "block";
        fetchEtIntelligence();
    }
    closeBtn.onclick = function() {
        modal.style.display = "none";
    }
    window.onclick = function(event) {
        if (event.target == modal) {
            modal.style.display = "none";
        }
    }
});

async function handleNpkSubmit(e) {
    e.preventDefault();
    const n = parseFloat(document.getElementById('input-n').value);
    const p = parseFloat(document.getElementById('input-p').value);
    const k = parseFloat(document.getElementById('input-k').value);

    try {
        const res = await fetch(`${API_BASE_URL}/sensors/nutrients`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ npk_n: n, npk_p: p, npk_k: k })
        });
        
        if (res.ok) {
            const data = await res.json();
            updateNpkGauges(data);
            addAlert('Manual nutrient levels updated successfully.', 'success');
            e.target.reset(); // clear form
        }
    } catch (error) {
        console.error('Error posting NPK:', error);
        addAlert('Failed to update nutrient levels.', 'critical');
    }
}

async function fetchNutrients() {
    try {
        const res = await fetch(`${API_BASE_URL}/sensors/nutrients/latest`);
        if (res.ok) {
            const data = await res.json();
            updateNpkGauges(data);
        }
    } catch (error) {
        console.log('No previous nutrient data found.');
    }
}

async function fetchData() {
    try {
        // Fetch latest history for charts
        const historyRes = await fetch(`${API_BASE_URL}/sensors/history?limit=20`);
        if (historyRes.ok) {
            const historyData = await historyRes.json();
            if (historyData.length > 0) {
                // Update Gauges with the most recent entry (last in the reversed array)
                const latest = historyData[historyData.length - 1];
                updateGauges(latest);
                
                // Update Charts
                if (window.updateCharts) {
                    window.updateCharts(historyData);
                }
                
                // Check alerts
                checkAlerts(latest);
            }
        }
        
        // Optionally fetch control schedule to show in logs
        const controlRes = await fetch(`${API_BASE_URL}/control/schedule?device_id=ESP32_01`);
        if (controlRes.ok) {
            const commands = await controlRes.json();
            commands.forEach(cmd => {
                addAlert(`Automated command issued: ${cmd.command_type}`, 'info');
            });
        }

        // Fetch Motor Runtime
        const runtimeRes = await fetch(`${API_BASE_URL}/control/runtime?device_id=ESP32_01`);
        if (runtimeRes.ok) {
            const runtimeData = await runtimeRes.json();
            updateActuatorUI(runtimeData);
        }

        // Fetch System Logs (Rain Delay, etc.)
        const logsRes = await fetch(`${API_BASE_URL}/sensors/logs?limit=5`);
        if (logsRes.ok) {
            const logs = await logsRes.json();
            logs.forEach(log => {
                // Use a key to prevent duplicate logs in UI
                const logKey = `log_${log.id}`;
                if (!window.displayedLogs) window.displayedLogs = new Set();
                
                if (!window.displayedLogs.has(logKey)) {
                    addAlert(log.message, log.level);
                    window.displayedLogs.add(logKey);
                }
            });
        }

    } catch (error) {
        console.error('Error fetching data:', error);
        document.getElementById('status-dot').style.backgroundColor = '#ef4444';
        document.getElementById('system-status-text').innerText = 'System Offline';
    }
}

function updateGauges(data) {
    document.getElementById('val-temp').innerText = `${data.temperature.toFixed(1)}°C`;
    document.getElementById('val-hum').innerText = `${data.humidity.toFixed(1)}%`;
    document.getElementById('val-soil').innerText = `${data.soil_moisture.toFixed(1)}%`;
    document.getElementById('val-lux').innerText = `${(data.lux || 0).toFixed(0)} lx`;
    
    // Render biological light metrics if available
    if (data.ppfd !== undefined) {
        document.getElementById('val-ppfd').innerText = data.ppfd.toFixed(1);
    }
    if (data.solar_radiation !== undefined) {
        document.getElementById('val-rad').innerText = data.solar_radiation.toFixed(1);
    }
    
    document.getElementById('status-dot').style.backgroundColor = '#10b981';
    document.getElementById('system-status-text').innerText = 'System Online';
}

function updateActuatorUI(data) {
    const led = document.getElementById('motor-led');
    const statusText = document.getElementById('motor-status-text');
    
    if (data.is_on) {
        led.classList.add('active');
        statusText.classList.add('active');
        statusText.innerText = 'ON';
    } else {
        led.classList.remove('active');
        statusText.classList.remove('active');
        statusText.innerText = 'OFF';
    }
    
    // Format mm:ss
    const curMins = Math.floor(data.current_runtime_seconds / 60);
    const curSecs = data.current_runtime_seconds % 60;
    document.getElementById('current-runtime').innerText = `${curMins.toString().padStart(2, '0')}:${curSecs.toString().padStart(2, '0')}`;
    
    // Format Total today
    const totMins = Math.floor(data.total_runtime_today_seconds / 60);
    document.getElementById('total-runtime').innerText = `${totMins}m`;

    // Format Biological Metrics
    if (data.total_water_pumped_grams !== undefined) {
        document.getElementById('total-water').innerText = `${data.total_water_pumped_grams}g`;
        document.getElementById('est-biomass').innerText = `${data.estimated_biomass_grams}g`;
        
        if (data.dynamic_threshold !== undefined) {
            document.getElementById('target-threshold').innerText = `${data.dynamic_threshold.toFixed(1)}%`;
        }
    }
}

async function fetchEtIntelligence() {
    try {
        const res = await fetch(`${API_BASE_URL}/weather/et_intelligence`);
        if (res.ok) {
            const data = await res.json();
            const content = document.getElementById('live-math-content');
            content.innerHTML = `
                <p><strong>Current Sensor & Weather Factors:</strong></p>
                <ul>
                    <li>Temperature: ${data.weather.temperature_c.toFixed(1)}°C</li>
                    <li>Humidity: ${data.weather.humidity_percent.toFixed(1)}%</li>
                    <li>Solar Radiation: ${data.weather.solar_radiation_wm2.toFixed(1)} W/m²</li>
                    <li>Wind Speed: ${data.weather.wind_speed_ms.toFixed(1)} m/s</li>
                </ul>
                <p><strong>Heuristic Variables:</strong></p>
                <ul>
                    <li>Reference ET (ET<sub>0</sub>): ${data.et_breakdown.et_0.toFixed(2)} mm/day</li>
                    <li>Crop Coefficient (K<sub>c</sub>): ${data.et_breakdown.kc.toFixed(2)}</li>
                </ul>
                <div class="formula">
                    <strong>Calculated ET<sub>c</sub>: ${data.et_breakdown.et_c.toFixed(2)} mm/day</strong>
                </div>
            `;
        }
    } catch (error) {
        document.getElementById('live-math-content').innerHTML = '<p>Error loading intelligence data.</p>';
    }
}

async function fetchWeatherForecast() {
    try {
        const res = await fetch(`${API_BASE_URL}/weather/hourly`);
        if (res.ok) {
            const data = await res.json();
            const container = document.getElementById('hourly-forecast-container');
            container.innerHTML = ''; // Clear loading text
            
            data.data.forEach(hour => {
                const card = document.createElement('div');
                card.className = 'weather-card';
                
                let icon = '☁️';
                if (hour.condition.includes("Sunny") || hour.condition.includes("Clear")) {
                    icon = hour.is_day ? '☀️' : '🌙';
                }
                
                card.innerHTML = `
                    <span class="weather-time">${hour.time_formatted}</span>
                    <span class="weather-icon">${icon}</span>
                    <span class="weather-temp">${hour.temperature_c}°C</span>
                    <span class="weather-hum">💧 ${hour.humidity_percent}%</span>
                `;
                
                container.appendChild(card);
            });
        }
    } catch (error) {
        console.error("Error fetching weather forecast:", error);
        document.getElementById('hourly-forecast-container').innerHTML = '<p>Error loading weather data.</p>';
    }
}

function updateNpkGauges(data) {
    document.getElementById('val-npk-n').innerText = `N: ${data.npk_n.toFixed(0)}`;
    document.getElementById('val-npk-p').innerText = `P: ${data.npk_p.toFixed(0)}`;
    document.getElementById('val-npk-k').innerText = `K: ${data.npk_k.toFixed(0)}`;
}

let lastAlertTime = 0;
function checkAlerts(data) {
    const now = Date.now();
    if (now - lastAlertTime < 10000) return; // Prevent spamming alerts every 5 seconds

    let alerted = false;
    if (data.temperature > 35) {
        addAlert(`Critical Temperature Detected: ${data.temperature.toFixed(1)}°C`, 'critical');
        alerted = true;
    }
    if (data.soil_moisture < 30) {
        addAlert(`Low Soil Moisture: ${data.soil_moisture.toFixed(1)}%`, 'warning');
        alerted = true;
    }
    
    if (alerted) {
        lastAlertTime = now;
    }
}

function addAlert(message, type = 'info') {
    const alertsLog = document.getElementById('alerts-log');
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert-item ${type}`;
    
    const timeString = new Date().toLocaleTimeString();
    alertDiv.innerHTML = `<strong>[${timeString}]</strong> ${message}`;
    
    alertsLog.prepend(alertDiv);
    
    // Keep only last 50 alerts
    if (alertsLog.children.length > 50) {
        alertsLog.removeChild(alertsLog.lastChild);
    }
}
