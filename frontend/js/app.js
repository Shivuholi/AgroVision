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

    if (infoBtn) {
        infoBtn.onclick = function() {
            modal.style.display = "block";
            fetchEtIntelligence();
        };
    }
    if (closeBtn) {
        closeBtn.onclick = function() {
            modal.style.display = "none";
        };
    }

    // Predictive Water Need Modal setup
    const waterModal = document.getElementById('water-modal');
    const waterInfoBtn = document.getElementById('water-info-btn');
    const waterCardBtn = document.getElementById('card-water-need');
    const closeWaterBtn = document.getElementById('close-water-modal');

    if (waterInfoBtn) {
        waterInfoBtn.onclick = function() {
            waterModal.style.display = "block";
            fetchWaterIntelligence();
        };
    }
    if (waterCardBtn) {
        waterCardBtn.onclick = function() {
            waterModal.style.display = "block";
            fetchWaterIntelligence();
        };
    }
    if (closeWaterBtn) {
        closeWaterBtn.onclick = function() {
            waterModal.style.display = "none";
        };
    }

    // Dynamic Threshold Modal setup
    const threshModal = document.getElementById('thresh-modal');
    const threshInfoBtn = document.getElementById('thresh-info-btn');
    const threshCardBtn = document.getElementById('card-target-threshold');
    const closeThreshBtn = document.getElementById('close-thresh-modal');

    if (threshInfoBtn) {
        threshInfoBtn.onclick = function() {
            threshModal.style.display = "block";
            fetchThreshIntelligence();
        };
    }
    if (threshCardBtn) {
        threshCardBtn.onclick = function() {
            threshModal.style.display = "block";
            fetchThreshIntelligence();
        };
    }
    if (closeThreshBtn) {
        closeThreshBtn.onclick = function() {
            threshModal.style.display = "none";
        };
    }

    window.onclick = function(event) {
        if (event.target == modal) {
            modal.style.display = "none";
        }
        if (event.target == waterModal) {
            waterModal.style.display = "none";
        }
        if (event.target == threshModal) {
            threshModal.style.display = "none";
        }
    };
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

        // FAILSAFE: If system is offline, force motor state to OFF and peripheral LOW
        const led = document.getElementById('motor-led');
        const statusText = document.getElementById('motor-status-text');
        const peripheralBadge = document.getElementById('motor-peripheral-badge');
        const curRuntime = document.getElementById('current-runtime');

        if (led) led.classList.remove('active');
        if (statusText) {
            statusText.classList.remove('active');
            statusText.innerText = 'OFF';
        }
        if (peripheralBadge) {
            peripheralBadge.innerText = 'PERIPHERAL: LOW (OFFLINE)';
            peripheralBadge.style.color = '#ef4444';
        }
        if (curRuntime) {
            curRuntime.innerText = '00:00';
        }
        const holdStateEl = document.getElementById('stat-hold-state');
        if (holdStateEl) {
            holdStateEl.innerText = 'OFFLINE';
            holdStateEl.style.color = '#ef4444';
        }
    }
}

function calculateContinuousDynamicThreshold(ppfd) {
    const p = (ppfd !== undefined && ppfd !== null) ? ppfd : 0.0;
    const threshold = 30.0 + (p / 1000.0) * 22.0;
    return Math.max(30.0, Math.min(52.0, threshold));
}

function updateGauges(data) {
    window.latestTelemetry = data;
    document.getElementById('val-temp').innerText = `${data.temperature.toFixed(1)}°C`;
    document.getElementById('val-hum').innerText = `${data.humidity.toFixed(1)}%`;
    document.getElementById('val-soil').innerText = `${data.soil_moisture.toFixed(1)}%`;
    document.getElementById('val-lux').innerText = `${(data.lux || 0).toFixed(0)} lx`;
    
    // Render biological light metrics if available
    let ppfd = data.ppfd;
    if (ppfd === undefined && data.lux !== undefined) {
        ppfd = data.lux * 0.0185;
    }
    if (ppfd !== undefined) {
        document.getElementById('val-ppfd').innerText = ppfd.toFixed(1);
    }
    if (data.solar_radiation !== undefined) {
        document.getElementById('val-rad').innerText = data.solar_radiation.toFixed(1);
    } else if (data.lux !== undefined) {
        document.getElementById('val-rad').innerText = (data.lux * 0.0079).toFixed(1);
    }
    
    // Update dynamic target moisture continuously using equation
    const dynamicThresh = calculateContinuousDynamicThreshold(ppfd);
    const targetEl = document.getElementById('target-threshold');
    if (targetEl) {
        targetEl.innerText = `${dynamicThresh.toFixed(1)}%`;
    }
    
    document.getElementById('status-dot').style.backgroundColor = '#10b981';
    document.getElementById('system-status-text').innerText = 'System Online';
}

function updateActuatorUI(data) {
    const led = document.getElementById('motor-led');
    const statusText = document.getElementById('motor-status-text');
    const peripheralBadge = document.getElementById('motor-peripheral-badge');
    const holdStateEl = document.getElementById('stat-hold-state');
    
    if (data.is_on) {
        if (led) led.classList.add('active');
        if (statusText) {
            statusText.classList.add('active');
            statusText.innerText = 'ON';
        }
        if (peripheralBadge) {
            peripheralBadge.innerText = 'PERIPHERAL: HIGH (ACTIVE)';
            peripheralBadge.style.color = 'var(--accent-green)';
        }
        if (holdStateEl) {
            holdStateEl.innerText = 'RUNNING';
            holdStateEl.style.color = 'var(--accent-green)';
        }
    } else {
        if (led) led.classList.remove('active');
        if (statusText) {
            statusText.classList.remove('active');
            statusText.innerText = 'OFF';
        }
        if (data.cooldown_remaining_seconds > 0) {
            if (peripheralBadge) {
                peripheralBadge.innerText = `PERIPHERAL: LOW (SOAK ${data.cooldown_remaining_seconds}s)`;
                peripheralBadge.style.color = 'var(--accent-warning)';
            }
            if (holdStateEl) {
                holdStateEl.innerText = `SOAK HOLD (${data.cooldown_remaining_seconds}s)`;
                holdStateEl.style.color = 'var(--accent-warning)';
            }
        } else {
            if (peripheralBadge) {
                peripheralBadge.innerText = 'PERIPHERAL: LOW (STANDBY)';
                peripheralBadge.style.color = 'var(--text-secondary)';
            }
            if (holdStateEl) {
                holdStateEl.innerText = 'STANDBY';
                holdStateEl.style.color = 'var(--text-secondary)';
            }
        }
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

    // Format Predictive Water Need
    if (data.water_need !== undefined) {
        updateWaterNeedUI(data.water_need);
    }
}

function updateWaterNeedUI(waterNeed) {
    const valEl = document.getElementById('val-water-need');
    const statusEl = document.getElementById('val-water-status');
    const barEl = document.getElementById('water-progress-bar');
    const statPctEl = document.getElementById('stat-water-pct');

    const pct = waterNeed.percentage !== undefined ? waterNeed.percentage : 0;
    
    if (valEl) valEl.innerText = `${pct.toFixed(0)}%`;
    if (statPctEl) statPctEl.innerText = `${pct.toFixed(0)}%`;
    if (statusEl) statusEl.innerText = waterNeed.status_label || 'Standard Demand';

    if (barEl) {
        barEl.style.width = `${Math.min(100, Math.max(0, pct))}%`;
        if (pct === 0) {
            barEl.style.background = '#64748b';
            if (valEl) valEl.style.color = '#94a3b8';
        } else if (pct > 100) {
            barEl.style.background = 'linear-gradient(90deg, #f59e0b, #ef4444)';
            if (valEl) valEl.style.color = '#f59e0b';
        } else if (pct < 50) {
            barEl.style.background = 'linear-gradient(90deg, #0284c7, #38bdf8)';
            if (valEl) valEl.style.color = '#38bdf8';
        } else {
            barEl.style.background = 'linear-gradient(90deg, #10b981, #34d399)';
            if (valEl) valEl.style.color = '#10b981';
        }
    }
}

async function fetchWaterIntelligence() {
    try {
        const res = await fetch(`${API_BASE_URL}/weather/water_recommendation?device_id=ESP32_01`);
        if (res.ok) {
            const resp = await res.json();
            renderWaterIntelligence(resp.data, resp.weather);
            return;
        }
        throw new Error("API returned non-200");
    } catch (error) {
        console.warn("Backend offline, using simulation for W_now:", error);
        // Fallback simulation so user can always view the math even before launching backend
        renderWaterIntelligence({
            w_now: 20.0,
            w_need: 100.0,
            percentage: 20.0,
            p_rain: 0.80,
            c_rain: 1.0,
            m_stress: 1.0,
            rain_reduction_factor: 0.20,
            status_label: "Rain Discount Active (-80%) [Simulation]",
            hours_until_rain: 3.5,
            soil_moisture: 32.0,
            target_threshold: 40.0
        }, {
            condition: "Rainy (Incoming in 3.5h)"
        });
    }
}

function renderWaterIntelligence(data, weather) {
    const content = document.getElementById('live-water-math-content');
    if (!content) return;
    
    let certaintyLabel = "High (0–6 hrs)";
    if (data.c_rain === 0.75) certaintyLabel = "Moderate (6–12 hrs)";
    else if (data.c_rain === 0.5) certaintyLabel = "Low (12–24 hrs)";
    else if (data.c_rain === 0) certaintyLabel = "None (>24 hrs)";

    let stressLabel = "Normal (1.0x)";
    if (data.m_stress > 1.0) stressLabel = "Severe Drought Buffer (1.2x)";
    else if (data.m_stress === 0.0) stressLabel = "Soil Damp (0.0x)";

    content.innerHTML = `
        <div class="formula-grid">
            <div class="formula-item">
                <div class="formula-item-label">Standard Volume (W<sub>need</sub>)</div>
                <div class="formula-item-val">${data.w_need}%</div>
                <div class="formula-item-sub">100% baseline cycle</div>
            </div>
            <div class="formula-item">
                <div class="formula-item-label">Rain Probability (P<sub>rain</sub>)</div>
                <div class="formula-item-val">${(data.p_rain * 100).toFixed(0)}%</div>
                <div class="formula-item-sub">Forecast: ${weather.condition}</div>
            </div>
            <div class="formula-item">
                <div class="formula-item-label">Rain Certainty (C<sub>rain</sub>)</div>
                <div class="formula-item-val">${data.c_rain.toFixed(2)}</div>
                <div class="formula-item-sub">${certaintyLabel} · In ~${data.hours_until_rain}h</div>
            </div>
            <div class="formula-item">
                <div class="formula-item-label">Plant Stress (M<sub>stress</sub>)</div>
                <div class="formula-item-val">${data.m_stress.toFixed(1)}&times;</div>
                <div class="formula-item-sub">${stressLabel} · Soil: ${data.soil_moisture}%</div>
            </div>
        </div>
        
        <div class="formula" style="color: var(--accent-blue);">
            <strong>Calculated W<sub>now</sub>: ${data.percentage}% of standard volume</strong>
        </div>

        <div style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.6; padding: 0.75rem; background: rgba(255,255,255,0.03); border-radius: 8px;">
            <div><strong>Step 1 (Rain Offset):</strong> 1 - (P<sub>rain</sub> &times; C<sub>rain</sub>) = 1 - (${data.p_rain} &times; ${data.c_rain}) = <strong>${data.rain_reduction_factor}</strong></div>
            <div><strong>Step 2 (Stress Multiply):</strong> ${data.w_need}% &times; ${data.rain_reduction_factor} &times; ${data.m_stress} = <strong style="color: var(--accent-blue);">${data.percentage}%</strong></div>
            <div style="margin-top: 5px; color: var(--accent-warning);"><strong>Status:</strong> ${data.status_label}</div>
        </div>
    `;
}

async function fetchThreshIntelligence() {
    let ppfd = 450.0;
    let soil = 32.0;
    let lux = 24300;

    if (window.latestTelemetry) {
        if (window.latestTelemetry.ppfd !== undefined) {
            ppfd = window.latestTelemetry.ppfd;
        } else if (window.latestTelemetry.lux !== undefined) {
            ppfd = window.latestTelemetry.lux * 0.0185;
        }
        if (window.latestTelemetry.soil_moisture !== undefined) {
            soil = window.latestTelemetry.soil_moisture;
        }
        if (window.latestTelemetry.lux !== undefined) {
            lux = window.latestTelemetry.lux;
        }
    }

    renderThreshIntelligence(ppfd, soil, lux);
}

function renderThreshIntelligence(ppfd, soil, lux) {
    const content = document.getElementById('live-thresh-math-content');
    if (!content) return;

    const stressAddition = (ppfd / 1000.0) * 22.0;
    const rawThreshold = 30.0 + stressAddition;
    const boundedThreshold = Math.max(30.0, Math.min(52.0, rawThreshold));

    const isWaterRequired = soil < boundedThreshold;
    const deficit = boundedThreshold - soil;

    let lightCondition = "Moderate Sunlight";
    if (ppfd < 100) lightCondition = "Low Light / Night Baseline";
    else if (ppfd < 400) lightCondition = "Diffused Light / Indoor / Early Morning";
    else if (ppfd < 800) lightCondition = "Bright Sunlight";
    else lightCondition = "Peak Solar Radiation Stress";

    content.innerHTML = `
        <div class="formula-grid">
            <div class="formula-item">
                <div class="formula-item-label">Baseline Threshold</div>
                <div class="formula-item-val">30.0%</div>
                <div class="formula-item-sub">Night/low-light minimum</div>
            </div>
            <div class="formula-item">
                <div class="formula-item-label">Measured Light (PPFD)</div>
                <div class="formula-item-val" style="color: var(--accent-warning);">${ppfd.toFixed(1)} <span style="font-size: 0.75rem;">μmol/m²s</span></div>
                <div class="formula-item-sub">${lightCondition} · ${lux.toFixed(0)} lx</div>
            </div>
            <div class="formula-item">
                <div class="formula-item-label">Light Stress Addition</div>
                <div class="formula-item-val">+${stressAddition.toFixed(1)}%</div>
                <div class="formula-item-sub">(PPFD / 1000 &times; 22%)</div>
            </div>
            <div class="formula-item">
                <div class="formula-item-label">Current Soil Moisture</div>
                <div class="formula-item-val" style="color: ${isWaterRequired ? 'var(--accent-warning)' : 'var(--accent-green)'};">${soil.toFixed(1)}%</div>
                <div class="formula-item-sub">${isWaterRequired ? 'Deficit: ' + deficit.toFixed(1) + '%' : 'Sufficient (+ ' + (-deficit).toFixed(1) + '%)'}</div>
            </div>
        </div>

        <div class="formula" style="color: var(--accent-warning);">
            <strong>Dynamic Target: 30% + (${ppfd.toFixed(1)} / 1000 &times; 22%) = ${boundedThreshold.toFixed(1)}%</strong>
        </div>

        <div style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.6; padding: 0.75rem; background: rgba(255,255,255,0.03); border-radius: 8px;">
            <div><strong>Continuous Equation:</strong> Target = 30.0% + (${ppfd.toFixed(1)} / 1000 &times; 22.0) = <strong>${rawThreshold.toFixed(2)}%</strong> (Bounded [30%, 52%] $\to$ <strong>${boundedThreshold.toFixed(1)}%</strong>)</div>
            <div style="margin-top: 8px; padding-top: 6px; border-top: 1px solid rgba(255,255,255,0.1);">
                <strong>Water Requirement Status:</strong><br>
                ${isWaterRequired 
                    ? `<span style="color: var(--accent-warning); font-weight: 700;">💧 WATER IS REQUIRED: Soil moisture (${soil.toFixed(1)}%) is BELOW dynamic threshold (${boundedThreshold.toFixed(1)}%). Irrigation demand triggered!</span>`
                    : `<span style="color: var(--accent-green); font-weight: 700;">🌱 WATER NOT REQUIRED: Soil moisture (${soil.toFixed(1)}%) meets or exceeds dynamic threshold (${boundedThreshold.toFixed(1)}%). Plant safely buffered.</span>`
                }
            </div>
        </div>
    `;
}

async function fetchEtIntelligence() {
    try {
        const res = await fetch(`${API_BASE_URL}/weather/et_intelligence`);
        if (res.ok) {
            const data = await res.json();
            renderEtIntelligence(data.weather, data.et_breakdown);
            return;
        }
        throw new Error("API returned non-200");
    } catch (error) {
        console.warn("Backend offline, using simulation for ET:", error);
        renderEtIntelligence(
            { temperature_c: 28.5, humidity_percent: 65.0, solar_radiation_wm2: 520.0, wind_speed_ms: 2.8 },
            { et_0: 4.12, kc: 1.20, et_c: 4.94 }
        );
    }
}

function renderEtIntelligence(weather, et_breakdown) {
    const content = document.getElementById('live-math-content');
    if (!content) return;
    content.innerHTML = `
        <p><strong>Current Sensor & Weather Factors:</strong></p>
        <ul>
            <li>Temperature: ${weather.temperature_c.toFixed(1)}°C</li>
            <li>Humidity: ${weather.humidity_percent.toFixed(1)}%</li>
            <li>Solar Radiation: ${weather.solar_radiation_wm2.toFixed(1)} W/m²</li>
            <li>Wind Speed: ${weather.wind_speed_ms.toFixed(1)} m/s</li>
        </ul>
        <p><strong>Heuristic Variables:</strong></p>
        <ul>
            <li>Reference ET (ET<sub>0</sub>): ${et_breakdown.et_0.toFixed(2)} mm/day</li>
            <li>Crop Coefficient (K<sub>c</sub>): ${et_breakdown.kc.toFixed(2)}</li>
        </ul>
        <div class="formula">
            <strong>Calculated ET<sub>c</sub>: ${et_breakdown.et_c.toFixed(2)} mm/day</strong>
        </div>
    `;
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
                    <span class="weather-rain" style="font-size: 0.75rem; color: var(--accent-blue); font-weight: 600;">🌧️ ${hour.rain_probability || 0}%</span>
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
