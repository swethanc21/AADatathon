// KSP Intelligent Crime Analytics & Field Reporting Platform - Frontend Engine

let crimeMap = null;
let pickerMap = null;
let pickerMarker = null;
let markerLayerGroup = null;
let routeLayerGroup = null;
let heatLayer = null;
let clusterLayerGroup = null;

let monthlyChart = null;
let divisionChart = null;
let crimeTypeChart = null;

let visNetworkInstance = null;

let masterCrimesData = [];
let currentAlertsData = [];

document.addEventListener("DOMContentLoaded", () => {
    initIcons();
    initClock();
    initTabs();
    initMaps();
    loadFilterOptions();
    loadMapData();
    loadDashboardData();
    loadAlertsFeed();
    initFormHandlers();
    initAIAssistant();
    initGlobalSearch();
    initProfileModal();
});

function initIcons() {
    if (window.lucide) {
        lucide.createIcons();
    }
}

function initClock() {
    const clockEl = document.getElementById("clock-display");
    function updateClock() {
        const now = new Date();
        clockEl.textContent = now.toLocaleTimeString() + " | " + now.toLocaleDateString();
    }
    updateClock();
    setInterval(updateClock, 1000);
}

function switchToTab(targetTab) {
    const navButtons = document.querySelectorAll(".nav-btn, .mobile-bottom-nav .nav-btn");
    const viewPanels = document.querySelectorAll(".view-panel");

    navButtons.forEach(b => b.classList.remove("active"));
    viewPanels.forEach(p => p.classList.remove("active"));

    document.querySelectorAll(`.nav-btn[data-tab="${targetTab}"]`).forEach(b => b.classList.add("active"));

    const activePanel = document.getElementById(targetTab);
    if (activePanel) activePanel.classList.add("active");

    if (targetTab === "map-view" && crimeMap) {
        setTimeout(() => crimeMap.invalidateSize(), 200);
    } else if (targetTab === "reporting-view" && pickerMap) {
        setTimeout(() => pickerMap.invalidateSize(), 200);
    } else if (targetTab === "ai-view") {
        loadNetworkGraph();
    }
}

function initTabs() {
    const navButtons = document.querySelectorAll(".nav-btn, .mobile-bottom-nav .nav-btn");

    navButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetTab = btn.getAttribute("data-tab");
            switchToTab(targetTab);
        });
    });
}

/* ==========================================================================
   MODULE 1: INTERACTIVE GEOSPATIAL MAP
   ========================================================================== */

const CITY_COORDINATES = {
    "Bengaluru": [12.9716, 77.5946, 12],
    "Mysuru": [12.2958, 76.6394, 13],
    "Mangaluru": [12.9141, 74.8560, 13],
    "Hubballi": [15.3647, 75.1240, 13],
    "Belagavi": [15.8497, 74.4977, 13],
    "Kalaburagi": [17.3297, 76.8343, 13],
    "Shivamogga": [13.9299, 75.5681, 13],
    "Davangere": [14.4644, 75.9218, 13],
    "Tumakuru": [13.3379, 77.1173, 13],
    "Ballari": [15.1394, 76.9214, 13],
    "Vijayapura": [16.8302, 75.7100, 13],
    "Udupi": [13.3409, 74.7421, 13],
    "Hassan": [13.0033, 76.1004, 13]
};

let mapZoomDebounce = null;

function initMaps() {
    // Karnataka State Center: Lat 14.50, Lng 75.80
    crimeMap = L.map("crime-map", {
        zoomControl: true,
        attributionControl: false,
        preferCanvas: true
    }).setView([14.50, 75.80], 7);

    L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
        maxZoom: 19,
        subdomains: 'abcd'
    }).addTo(crimeMap);

    markerLayerGroup = L.layerGroup().addTo(crimeMap);
    routeLayerGroup = L.layerGroup().addTo(crimeMap);
    clusterLayerGroup = L.layerGroup().addTo(crimeMap);

    // Zoom and pan dynamic thresholding listener for zero-lag performance
    crimeMap.on("zoomend moveend", () => {
        clearTimeout(mapZoomDebounce);
        mapZoomDebounce = setTimeout(() => {
            if (masterCrimesData && masterCrimesData.length > 0) {
                renderMapMarkers(masterCrimesData);
            }
        }, 150);
    });

    // Mini Map for Field Incident Location Picker
    pickerMap = L.map("picker-map", {
        zoomControl: true,
        attributionControl: false
    }).setView([12.9716, 77.5946], 12);

    L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
        maxZoom: 19
    }).addTo(pickerMap);

    pickerMarker = L.marker([12.9716, 77.5946], { draggable: true }).addTo(pickerMap);

    pickerMarker.on("dragend", (e) => {
        const coord = e.target.getLatLng();
        document.getElementById("rep-lat").value = coord.lat.toFixed(6);
        document.getElementById("rep-lng").value = coord.lng.toFixed(6);
    });

    pickerMap.on("click", (e) => {
        const lat = e.latlng.lat;
        const lng = e.latlng.lng;
        pickerMarker.setLatLng([lat, lng]);
        document.getElementById("rep-lat").value = lat.toFixed(6);
        document.getElementById("rep-lng").value = lng.toFixed(6);
    });
}

async function loadFilterOptions() {
    try {
        const res = await fetch("/api/stats/dashboard");
        const data = await res.json();
        
        const divSelect = document.getElementById("filter-division");
        data.by_division.forEach(d => {
            if (d.division) {
                const opt = document.createElement("option");
                opt.value = d.division;
                opt.textContent = d.division;
                divSelect.appendChild(opt);
            }
        });

        const typeSelect = document.getElementById("filter-crime-type");
        data.by_crime_type.forEach(ct => {
            if (ct.crime_type) {
                const opt = document.createElement("option");
                opt.value = ct.crime_type;
                opt.textContent = ct.crime_type;
                typeSelect.appendChild(opt);
            }
        });
    } catch (e) {
        console.error("Error loading filter options:", e);
    }
}

async function loadMapData() {
    const div = document.getElementById("filter-division")?.value || "All";
    const city = document.getElementById("filter-city")?.value || "All";
    const type = document.getElementById("filter-crime-type")?.value || "All";
    const sev = document.getElementById("filter-severity")?.value || "All";
    const stat = document.getElementById("filter-status")?.value || "All";
    const kw = document.getElementById("filter-keyword-search")?.value.trim();

    let url = `/api/crimes?limit=2500`;
    if (div !== "All") url += `&division=${encodeURIComponent(div)}`;
    if (city !== "All") url += `&city=${encodeURIComponent(city)}`;
    if (type !== "All") url += `&crime_type=${encodeURIComponent(type)}`;
    if (sev !== "All") url += `&severity=${encodeURIComponent(sev)}`;
    if (stat !== "All") url += `&status=${encodeURIComponent(stat)}`;
    if (kw) url += `&q=${encodeURIComponent(kw)}`;

    try {
        const res = await fetch(url);
        const json = await res.json();
        masterCrimesData = json.data || [];

        renderMapMarkers(masterCrimesData);
        loadHotspotClusters();
    } catch (e) {
        console.error("Error fetching map data:", e);
    }
}

function getSVGIconForCrimeType(crimeType, sevClass) {
    const type = (crimeType || '').toLowerCase();
    let svgPath = `<circle cx="12" cy="12" r="5" fill="currentColor"/>`;
    if (type.includes("theft") || type.includes("burglary")) {
        svgPath = `<path d="M12 2L3 7v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7l-9-5z" fill="none" stroke="currentColor" stroke-width="2"/>`;
    } else if (type.includes("robbery") || type.includes("assault") || type.includes("murder")) {
        svgPath = `<polygon points="12,2 15,8 22,9 17,14 18,21 12,17 6,21 7,14 2,9 9,8" fill="currentColor"/>`;
    } else if (type.includes("vehicle")) {
        svgPath = `<path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.5 3.1C1.4 11.4 1 12.2 1 13v3c0 .6.4 1 1 1h2m15 0a2 2 2 0 1 0 0-4 2 2 0 0 0 0 4zm-14 0a2 2 2 0 1 0 0-4 2 2 0 0 0 0 4z" fill="none" stroke="currentColor" stroke-width="2"/>`;
    } else if (type.includes("cyber") || type.includes("drug")) {
        svgPath = `<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><line x1="12" y1="8" x2="12" y2="12" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="16" r="1" fill="currentColor"/>`;
    }

    return `
        <div class="svg-pin-wrap ${sevClass}">
            <div class="svg-pin-ring"></div>
            <div class="svg-pin-core">
                <svg width="16" height="16" viewBox="0 0 24 24">${svgPath}</svg>
            </div>
        </div>
    `;
}

function renderMapMarkers(crimes) {
    markerLayerGroup.clearLayers();
    if (heatLayer) {
        crimeMap.removeLayer(heatLayer);
        heatLayer = null;
    }

    const showMarkers = document.getElementById("layer-toggle-markers").checked;
    const showHeatmap = document.getElementById("layer-toggle-heatmap").checked;

    const heatPoints = [];
    const zoom = crimeMap ? crimeMap.getZoom() : 7;
    const bounds = crimeMap ? crimeMap.getBounds() : null;

    const cityVal = document.getElementById("filter-city")?.value || "All";
    const divVal = document.getElementById("filter-division")?.value || "All";
    const typeVal = document.getElementById("filter-crime-type")?.value || "All";
    const kwVal = document.getElementById("filter-keyword-search")?.value.trim();

    const isFiltered = (cityVal !== "All" || divVal !== "All" || typeVal !== "All" || (kwVal && kwVal.length > 0));

    let renderCount = 0;

    crimes.forEach((c, idx) => {
        const lat = c.latitude;
        const lng = c.longitude;
        if (!lat || !lng) return;

        const sevClass = (c.severity || "medium").toLowerCase();

        let inViewport = true;
        if (bounds) {
            inViewport = bounds.contains([lat, lng]);
        }

        const shouldRenderPin = showMarkers && inViewport && (zoom >= 9.5 || isFiltered || renderCount < 150);

        if (shouldRenderPin) {
            renderCount++;
            let customIcon;
            if (c.suspect_name && idx % 7 === 0) {
                const avatarUrl = `https://images.unsplash.com/photo-${1534528741775 + (idx*100)}?auto=format&fit=crop&w=150&q=80`;
                customIcon = L.divIcon({
                    html: `<div class="suspect-avatar-pin"><img src="${avatarUrl}" alt="Suspect Avatar"></div>`,
                    className: "ksp-custom-pin",
                    iconSize: [42, 42]
                });
            } else {
                customIcon = L.divIcon({
                    html: getSVGIconForCrimeType(c.crime_type, sevClass),
                    className: "ksp-custom-pin",
                    iconSize: [34, 34]
                });
            }

            const popupContent = `
                <div class="map-popup-card">
                    <div class="popup-title">${c.crime_type}</div>
                    <div class="popup-row"><strong>Case ID:</strong> ${c.case_id}</div>
                    <div class="popup-row"><strong>Division/City:</strong> ${c.division || c.city || 'Karnataka'} (${c.station_id})</div>
                    <div class="popup-row"><strong>Date:</strong> ${c.date_time}</div>
                    <div class="popup-row"><strong>Status:</strong> ${c.status}</div>
                    ${c.suspect_name ? `<div class="popup-row" style="color: #ef4444;"><strong>Suspect:</strong> ${c.suspect_name}</div>` : ''}
                    ${c.amount_involved ? `<div class="popup-row"><strong>Loss:</strong> ₹${c.amount_involved.toLocaleString()}</div>` : ''}
                    <button class="btn-profile-popup" onclick="openCriminalProfileModalByCase('${c.case_id}')">
                        Inspect Criminal Profile &rarr;
                    </button>
                </div>
            `;

            const marker = L.marker([lat, lng], { icon: customIcon }).bindPopup(popupContent);
            markerLayerGroup.addLayer(marker);
        }

        let intensity = 0.5;
        if (sevClass === "critical") intensity = 1.0;
        else if (sevClass === "high") intensity = 0.8;
        else if (sevClass === "medium") intensity = 0.5;
        else intensity = 0.3;

        heatPoints.push([lat, lng, intensity]);
    });

    if (showHeatmap && heatPoints.length > 0) {
        heatLayer = L.heatLayer(heatPoints, {
            radius: 25,
            blur: 15,
            maxZoom: 14,
            gradient: { 0.4: '#10b981', 0.65: '#f59e0b', 1.0: '#ef4444' }
        }).addTo(crimeMap);
    }

    renderSuspectTrackingRoutes(crimes);
    document.getElementById("map-active-count").textContent = crimes.length;
}

function renderSuspectTrackingRoutes(crimes) {
    routeLayerGroup.clearLayers();
    const routeToggle = document.getElementById("layer-toggle-routes");
    const showRoutes = routeToggle ? routeToggle.checked : true;
    if (!showRoutes) return;

    const suspectGroups = {};
    crimes.forEach(c => {
        const key = c.suspect_id ? `SUSP_${c.suspect_id}` : (c.mo_signature && c.mo_signature !== "Standard Incident" ? `MO_${c.mo_signature}` : null);
        if (key) {
            if (!suspectGroups[key]) suspectGroups[key] = [];
            suspectGroups[key].push(c);
        }
    });

    Object.keys(suspectGroups).forEach(key => {
        const group = suspectGroups[key];
        if (group.length >= 2) {
            group.sort((a, b) => new Date(a.date_time) - new Date(b.date_time));
            const latlngs = group.map(c => [c.latitude, c.longitude]);
            
            const polyline = L.polyline(latlngs, {
                color: '#38bdf8',
                weight: 3,
                opacity: 0.85,
                dashArray: '8, 8'
            });
            routeLayerGroup.addLayer(polyline);
        }
    });
}

async function loadHotspotClusters() {
    clusterLayerGroup.clearLayers();
    const showClusters = document.getElementById("layer-toggle-clusters").checked;
    if (!showClusters) return;

    const div = document.getElementById("filter-division").value;
    const type = document.getElementById("filter-crime-type").value;
    const sev = document.getElementById("filter-severity").value;
    const stat = document.getElementById("filter-status").value;
    const kw = document.getElementById("filter-keyword-search")?.value.trim();

    let url = `/api/analytics/hotspots?eps_km=1.8&min_samples=4`;
    if (div !== "All") url += `&division=${encodeURIComponent(div)}`;
    if (type !== "All") url += `&crime_type=${encodeURIComponent(type)}`;
    if (sev !== "All") url += `&severity=${encodeURIComponent(sev)}`;
    if (stat !== "All") url += `&status=${encodeURIComponent(stat)}`;
    if (kw) url += `&q=${encodeURIComponent(kw)}`;

    try {
        const res = await fetch(url);
        const json = await res.json();
        const clusters = json.data?.clusters || [];

        document.getElementById("map-clusters-count").textContent = clusters.length;

        clusters.forEach(cls => {
            const circle = L.circle([cls.centroid_lat, cls.centroid_lng], {
                color: "#f59e0b",
                fillColor: "#f59e0b",
                fillOpacity: 0.18,
                radius: 1500
            });

            circle.bindPopup(`
                <div style="color: #000;">
                    <h4 style="color: #b45309; margin-bottom: 4px;">DBSCAN Cluster #${cls.cluster_id}</h4>
                    <div><strong>Incident Count:</strong> ${cls.crime_count} crimes</div>
                    <div><strong>Primary Offense:</strong> ${cls.primary_crime_type}</div>
                    <div><strong>Division:</strong> ${cls.division}</div>
                    <div><strong>Risk Level:</strong> ${cls.risk_level}</div>
                </div>
            `);

            clusterLayerGroup.addLayer(circle);
        });
    } catch (e) {
        console.error("Error loading DBSCAN clusters:", e);
    }
}

/* ==========================================================================
   MODULE 2: 3-YEAR TREND DASHBOARD
   ========================================================================== */

async function loadDashboardData() {
    try {
        const res = await fetch("/api/stats/dashboard");
        const data = await res.json();

        document.getElementById("kpi-total-crimes").textContent = data.kpi.total_crimes.toLocaleString();
        document.getElementById("kpi-solved-cases").textContent = data.kpi.solved.toLocaleString();
        document.getElementById("kpi-resolution-rate").textContent = `${data.kpi.resolution_rate}% Resolution Rate`;
        document.getElementById("kpi-under-inv").textContent = data.kpi.under_investigation.toLocaleString();
        document.getElementById("kpi-financial-loss").textContent = `₹${(data.kpi.total_monetary_loss / 100000).toFixed(1)} Lakhs`;

        renderMonthlyChart(data.timeline);
        renderDivisionChart(data.by_division);
        renderCrimeTypeChart(data.by_crime_type);
        renderHistoricalTable(data.district_historical);
    } catch (e) {
        console.error("Error loading dashboard stats:", e);
    }
}

function renderMonthlyChart(timeline) {
    const ctx = document.getElementById("monthlyTrendChart").getContext("2d");
    if (monthlyChart) monthlyChart.destroy();

    monthlyChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: timeline.map(t => t.month),
            datasets: [{
                label: 'Monthly Crime Count',
                data: timeline.map(t => t.count),
                borderColor: '#4f46e5',
                backgroundColor: 'rgba(79, 70, 229, 0.12)',
                fill: true,
                tension: 0.4,
                borderWidth: 3,
                pointBackgroundColor: '#4f46e5'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { color: '#0f172a', font: { family: 'Poppins', weight: '600' } } } },
            scales: {
                x: { ticks: { color: '#64748b', font: { family: 'Poppins' } }, grid: { color: '#f1f5f9' } },
                y: { ticks: { color: '#64748b', font: { family: 'Poppins' } }, grid: { color: '#f1f5f9' } }
            }
        }
    });
}

function renderDivisionChart(byDiv) {
    const ctx = document.getElementById("divisionChart").getContext("2d");
    if (divisionChart) divisionChart.destroy();

    const topDivs = byDiv.slice(0, 8);
    divisionChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: topDivs.map(d => d.division || "Other"),
            datasets: [{
                label: 'Crime Count',
                data: topDivs.map(d => d.count),
                backgroundColor: '#6366f1',
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: '#64748b', font: { family: 'Poppins' } }, grid: { display: false } },
                y: { ticks: { color: '#64748b', font: { family: 'Poppins' } }, grid: { color: '#f1f5f9' } }
            }
        }
    });
}

function renderCrimeTypeChart(byType) {
    const ctx = document.getElementById("crimeTypeChart").getContext("2d");
    if (crimeTypeChart) crimeTypeChart.destroy();

    const topTypes = byType.slice(0, 6);
    crimeTypeChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: topTypes.map(t => t.crime_type),
            datasets: [{
                data: topTypes.map(t => t.count),
                backgroundColor: ['#4f46e5', '#7c3aed', '#0284c7', '#10b981', '#f59e0b', '#ef4444']
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'right', labels: { color: '#0f172a', font: { family: 'Poppins', size: 11, weight: '600' } } } }
        }
    });
}

function renderHistoricalTable(rows) {
    const tbody = document.querySelector("#district-trend-table tbody");
    if (!tbody) return;
    tbody.innerHTML = "";

    rows.forEach((r, idx) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${idx + 1}</td>
            <td><strong>${r.district}</strong></td>
            <td>${r.ipc_bns_crimes.toLocaleString()}</td>
            <td>${r.sll_crimes.toLocaleString()}</td>
            <td>${r.year}</td>
        `;
        tbody.appendChild(tr);
    });
}

/* ==========================================================================
   MODULE 3: FIELD REPORTING & FORM HANDLERS
   ========================================================================== */

function initFormHandlers() {
    // 1. Geolocation Fetch Button
    document.getElementById("detect-gps-btn").addEventListener("click", () => {
        const statusLbl = document.getElementById("gps-status-lbl");
        statusLbl.textContent = "Requesting GPS coordinates from device...";

        if (!navigator.geolocation) {
            statusLbl.textContent = "Geolocation API not supported by browser.";
            return;
        }

        navigator.geolocation.getCurrentPosition(
            (pos) => {
                const lat = pos.coords.latitude;
                const lng = pos.coords.longitude;
                document.getElementById("rep-lat").value = lat.toFixed(6);
                document.getElementById("rep-lng").value = lng.toFixed(6);
                statusLbl.textContent = `GPS Fix Acquired: (${lat.toFixed(4)}, ${lng.toFixed(4)})`;

                pickerMarker.setLatLng([lat, lng]);
                pickerMap.setView([lat, lng], 14);
            },
            (err) => {
                statusLbl.textContent = `GPS Error: ${err.message}. Defaulting to Karnataka center.`;
            },
            { timeout: 10000, enableHighAccuracy: true }
        );
    });

    // 2. Incident Form Submission
    document.getElementById("incident-report-form").addEventListener("submit", async (e) => {
        e.preventDefault();

        const payload = {
            crime_type: document.getElementById("rep-crime-type").value,
            severity: document.getElementById("rep-severity").value,
            division: document.getElementById("rep-division").value,
            station_id: document.getElementById("rep-station").value,
            latitude: parseFloat(document.getElementById("rep-lat").value),
            longitude: parseFloat(document.getElementById("rep-lng").value),
            date_time: document.getElementById("rep-datetime").value || null,
            amount_involved: parseFloat(document.getElementById("rep-amount").value) || 0.0,
            mo_signature: document.getElementById("rep-mo").value || "Standard Incident",
            description: document.getElementById("rep-desc").value
        };

        try {
            const res = await fetch("/api/crimes/report", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            const json = await res.json();
            alert(`Report Submitted! Case ID: ${json.case_id}`);

            loadMapData();
            loadDashboardData();
            loadAlertsFeed();

            document.getElementById("incident-report-form").reset();
        } catch (err) {
            console.error("Error submitting report:", err);
            alert("Failed to submit incident report.");
        }
    });

    // Filters Apply & Reset
    const kwInput = document.getElementById("filter-keyword-search");
    let filterDebounce;
    if (kwInput) {
        kwInput.addEventListener("input", () => {
            clearTimeout(filterDebounce);
            filterDebounce = setTimeout(loadMapData, 300);
        });
    }

    document.getElementById("apply-filters-btn").addEventListener("click", loadMapData);
    document.getElementById("reset-filters-btn").addEventListener("click", () => {
        if (kwInput) kwInput.value = "";
        document.getElementById("filter-division").value = "All";
        document.getElementById("filter-crime-type").value = "All";
        document.getElementById("filter-severity").value = "All";
        document.getElementById("filter-status").value = "All";
        loadMapData();
    });

    // Resolution Search & Update
    document.getElementById("res-search-btn").addEventListener("click", lookupCaseForResolution);
    document.getElementById("resolution-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const caseId = document.getElementById("res-card-id").textContent;
        const payload = {
            status: document.getElementById("res-status-select").value,
            suspect_id: document.getElementById("res-suspect-id").value,
            suspect_name: document.getElementById("res-suspect-name").value,
            amount_recovered: parseFloat(document.getElementById("res-recovered-amount").value) || 0,
            resolution_notes: document.getElementById("res-notes").value
        };

        try {
            const res = await fetch(`/api/crimes/${caseId}/resolve`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const json = await res.json();
            alert(json.message || "Case Resolution Updated!");

            loadMapData();
            loadDashboardData();
        } catch (e) {
            alert("Error updating resolution.");
        }
    });
}

async function lookupCaseForResolution() {
    const q = document.getElementById("res-search-input").value.trim();
    if (!q) return;

    try {
        const res = await fetch(`/api/crimes?q=${encodeURIComponent(q)}&limit=10`);
        const json = await res.json();
        const match = json.data && json.data.length > 0 ? json.data[0] : null;

        if (match) {
            document.getElementById("res-case-card").classList.remove("hidden");
            document.getElementById("res-card-id").textContent = match.case_id;
            document.getElementById("res-card-title").textContent = `${match.crime_type} (${match.status})`;
            document.getElementById("res-card-status").textContent = match.status;
            document.getElementById("res-card-div").textContent = match.division;
            document.getElementById("res-card-station").textContent = match.station_id;
            document.getElementById("res-card-date").textContent = match.date_time;
            document.getElementById("res-card-sev").textContent = match.severity;
            document.getElementById("res-card-coords").textContent = `${match.latitude.toFixed(4)}, ${match.longitude.toFixed(4)}`;
            document.getElementById("res-card-mo").textContent = match.mo_signature || 'N/A';
        } else {
            alert("Case not found matching search query.");
        }
    } catch (e) {
        console.error("Resolution lookup error:", e);
    }
}

/* ==========================================================================
   MODULE 5: ML ALERTS FEED
   ========================================================================== */

async function loadAlertsFeed() {
    try {
        const res = await fetch("/api/alerts?limit=25");
        const json = await res.json();
        currentAlertsData = json.data || [];

        const countBadge = document.getElementById("alert-badge-count");
        if (countBadge) countBadge.textContent = currentAlertsData.length;

        const container = document.getElementById("alerts-feed-container");
        if (!container) return;
        container.innerHTML = "";

        if (currentAlertsData.length === 0) {
            container.innerHTML = `<div style="color: #94a3b8; text-align: center; padding: 40px;">No ML alerts generated yet. File new incident reports to trigger DBSCAN pattern matching.</div>`;
            return;
        }

        currentAlertsData.forEach(alt => {
            const card = document.createElement("div");
            card.className = "alert-card";
            card.innerHTML = `
                <div>
                    <span class="alert-type-badge">${alt.alert_type}</span>
                    <h4 style="margin: 8px 0; color: #f8fafc;">${alt.message}</h4>
                    <div style="font-size: 0.8rem; color: #94a3b8;">
                        <strong>Matched Case IDs:</strong> <span style="color: #f59e0b;">${alt.matched_case_ids}</span> | 
                        <strong>Distance:</strong> ${alt.distance_meters ? Math.round(alt.distance_meters) + 'm' : 'N/A'} | 
                        <strong>Time:</strong> ${alt.created_at}
                    </div>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 1.1rem; font-weight: 800; color: #ef4444;">${Math.round(alt.confidence_score * 100)}%</div>
                    <span style="font-size: 0.75rem; color: #94a3b8;">Confidence Score</span>
                </div>
            `;
            container.appendChild(card);
        });
    } catch (e) {
        console.error("Error loading alerts feed:", e);
    }
}

/* ==========================================================================
   MODULE 6: AI ASSISTANT & GRAPH NETWORK
   ========================================================================== */

function initAIAssistant() {
    const chatInput = document.getElementById("ai-chat-input");
    const sendBtn = document.getElementById("ai-send-btn");
    const voiceBtn = document.getElementById("voice-input-btn");
    const exportPdfBtn = document.getElementById("export-pdf-btn");

    // Language Toggle Listener
    let activeVoiceLang = "en-IN";
    const btnEn = document.getElementById("btn-lang-en");
    const btnKn = document.getElementById("btn-lang-kn");
    if (btnEn && btnKn) {
        btnEn.addEventListener("click", () => {
            btnEn.classList.add("active");
            btnKn.classList.remove("active");
            activeVoiceLang = "en-IN";
            chatInput.placeholder = "Ask a crime question in English (e.g. Show theft cases in Mysuru)...";
            if (voiceBtn) voiceBtn.title = "Voice Input (English: en-IN)";
        });
        btnKn.addEventListener("click", () => {
            btnKn.classList.add("active");
            btnEn.classList.remove("active");
            activeVoiceLang = "kn-IN";
            chatInput.placeholder = "ಪ್ರಶ್ನೆಯನ್ನು ಕನ್ನಡದಲ್ಲಿ ಕೇಳಿ (ಉದಾ: ಮೈಸೂರಿನಲ್ಲಿ ಕಳವು ಪ್ರಕರಣಗಳು)...";
            if (voiceBtn) voiceBtn.title = "ಧ್ವನಿ ಹುಡುಕಾಟ (Kannada: kn-IN)";
        });
    }

    if (exportPdfBtn) {
        exportPdfBtn.addEventListener("click", exportConversationPDF);
    }

    document.querySelectorAll(".prompt-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            const prompt = chip.getAttribute("data-prompt");
            chatInput.value = prompt;
            sendAIQuery(prompt);
        });
    });

    if (sendBtn) {
        sendBtn.addEventListener("click", () => {
            const q = chatInput.value.trim();
            if (q) sendAIQuery(q);
        });
    }

    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            const q = chatInput.value.trim();
            if (q) sendAIQuery(q);
        }
    });

    // Native 16-bit PCM WAV Audio Recording & Speech Transcription Engine
    let isRecording = false;
    let micStream = null;
    let audioCtx = null;
    let micSource = null;
    let scriptProc = null;
    let rawPcmSamples = [];
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition = null;
    let finalTranscript = "";

    if (SpeechRecognition) {
        try {
            recognition = new SpeechRecognition();
            recognition.continuous = true;
            recognition.interimResults = true;

            recognition.onstart = () => {
                isRecording = true;
                voiceBtn.classList.add("recording");
                chatInput.value = "";
                finalTranscript = "";
                const isKn = (btnKn && btnKn.classList.contains("active")) || activeVoiceLang === "kn-IN";
                chatInput.placeholder = isKn ? "🎙️ ಧ್ವನಿ ರೆಕಾರ್ಡ್ ಆಗುತ್ತಿದೆ... ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡಿ... (ಮುಗಿಸಲು ಮೈಕ್ ಕ್ಲಿಕ್ ಮಾಡಿ)" : "🎙️ Listening... Speak your question in English... (Click Mic when done)";
            };

            recognition.onresult = (event) => {
                let interimTranscript = "";
                for (let i = event.resultIndex; i < event.results.length; ++i) {
                    if (event.results[i].isFinal) {
                        finalTranscript += event.results[i][0].transcript + " ";
                    } else {
                        interimTranscript += event.results[i][0].transcript;
                    }
                }
                const fullText = (finalTranscript + interimTranscript).trim();
                if (fullText) {
                    chatInput.value = fullText;
                }
            };

            recognition.onend = () => {
                isRecording = false;
                voiceBtn.classList.remove("recording");
                chatInput.placeholder = "Ask a crime question in English or Kannada...";
                const text = chatInput.value.trim();
                if (text) {
                    sendAIQuery(text);
                }
            };

            recognition.onerror = (event) => {
                console.warn("Web Speech API notice:", event.error);
                // On SpeechRecognition error, rely on AudioContext PCM WAV recorder
            };
        } catch (e) {
            console.warn("SpeechRecognition init note:", e);
        }
    }

    function createPcmWavBlob(samples, sampleRate) {
        const buffer = new ArrayBuffer(44 + samples.length * 2);
        const view = new DataView(buffer);

        function writeString(offset, string) {
            for (let i = 0; i < string.length; i++) {
                view.setUint8(offset + i, string.charCodeAt(i));
            }
        }

        writeString(0, 'RIFF');
        view.setUint32(4, 36 + samples.length * 2, true);
        writeString(8, 'WAVE');
        writeString(12, 'fmt ');
        view.setUint32(16, 16, true);
        view.setUint16(20, 1, true); // PCM
        view.setUint16(22, 1, true); // Mono
        view.setUint32(24, sampleRate, true);
        view.setUint32(28, sampleRate * 2, true);
        view.setUint16(32, 2, true);
        view.setUint16(34, 16, true);
        writeString(36, 'data');
        view.setUint32(40, samples.length * 2, true);

        let offset = 44;
        for (let i = 0; i < samples.length; i++, offset += 2) {
            const s = Math.max(-1, Math.min(1, samples[i]));
            view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
        }

        return new Blob([view], { type: 'audio/wav' });
    }

    async function sendPcmWavAudioForTranscription() {
        if (rawPcmSamples.length === 0) return;

        let totalLength = 0;
        for (let i = 0; i < rawPcmSamples.length; i++) {
            totalLength += rawPcmSamples[i].length;
        }

        const merged = new Float32Array(totalLength);
        let offset = 0;
        for (let i = 0; i < rawPcmSamples.length; i++) {
            merged.set(rawPcmSamples[i], offset);
            offset += rawPcmSamples[i].length;
        }

        const wavBlob = createPcmWavBlob(merged, 16000);
        const formData = new FormData();
        formData.append("file", wavBlob, "speech.wav");

        chatInput.placeholder = "Transcribing voice speech...";
        try {
            const res = await fetch(`/api/ai/transcribe?language=${activeVoiceLang}`, {
                method: "POST",
                body: formData
            });
            const json = await res.json();
            if (json.transcribed_text && json.transcribed_text.trim()) {
                chatInput.value = json.transcribed_text.trim();
                sendAIQuery(json.transcribed_text.trim());
            } else {
                chatInput.placeholder = "Speech not recognized. Please speak clearly into the mic.";
            }
        } catch (err) {
            console.error("Transcription error:", err);
            chatInput.placeholder = "Ask a crime question in English or Kannada...";
        }
    }

    voiceBtn.addEventListener("click", async () => {
        if (!isRecording) {
            const isKn = (btnKn && btnKn.classList.contains("active")) || activeVoiceLang === "kn-IN";
            activeVoiceLang = isKn ? "kn-IN" : "en-IN";

            // Request microphone access
            try {
                micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            } catch (err) {
                console.warn("Mic access permission error:", err);
                chatInput.placeholder = "Microphone access denied. Please allow mic in browser settings.";
                return;
            }

            isRecording = true;
            voiceBtn.classList.add("recording");
            chatInput.value = "";
            chatInput.placeholder = isKn ? "🎙️ ಧ್ವನಿ ರೆಕಾರ್ಡ್ ಆಗುತ್ತಿದೆ... ಮಾತನಾಡಿ..." : "🎙️ Recording audio... Speak your question now...";

            // Start AudioContext 16kHz PCM Sampler
            try {
                rawPcmSamples = [];
                audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
                micSource = audioCtx.createMediaStreamSource(micStream);
                scriptProc = audioCtx.createScriptProcessor(4096, 1, 1);

                scriptProc.onaudioprocess = (e) => {
                    if (!isRecording) return;
                    const inputData = e.inputBuffer.getChannelData(0);
                    rawPcmSamples.push(new Float32Array(inputData));
                };

                micSource.connect(scriptProc);
                scriptProc.connect(audioCtx.destination);
            } catch (e) {
                console.warn("AudioContext setup note:", e);
            }

            // Also trigger Web Speech API simultaneously if supported
            if (recognition) {
                recognition.lang = activeVoiceLang;
                try {
                    recognition.start();
                } catch (e) {}
            }
        } else {
            // Stop Recording
            isRecording = false;
            voiceBtn.classList.remove("recording");

            if (recognition) {
                try { recognition.stop(); } catch (e) {}
            }

            if (scriptProc) {
                try { scriptProc.disconnect(); } catch (e) {}
            }
            if (micSource) {
                try { micSource.disconnect(); } catch (e) {}
            }
            if (micStream) {
                try { micStream.getTracks().forEach(t => t.stop()); } catch (e) {}
            }
            if (audioCtx) {
                try { audioCtx.close(); } catch (e) {}
            }

            const currentVal = chatInput.value.trim();
            if (currentVal) {
                sendAIQuery(currentVal);
            } else {
                // If WebSpeech did not capture text, send PCM WAV Blob to backend!
                sendPcmWavAudioForTranscription();
            }
        }
    });

    const loadGraphBtn = document.getElementById("load-graph-btn");
    if (loadGraphBtn) loadGraphBtn.addEventListener("click", loadNetworkGraph);
}

function appendUserChatMessage(text) {
    const thread = document.getElementById("ai-chat-thread");
    if (!thread) return;

    const userBubble = document.createElement("div");
    userBubble.className = "chat-message user-message";
    userBubble.innerHTML = `
        <div class="message-avatar"><i data-lucide="user"></i></div>
        <div class="message-body">
            <div class="message-sender">Investigating Officer <span class="badge-tag">User</span></div>
            <div class="message-text">${text}</div>
        </div>
    `;
    thread.appendChild(userBubble);
    thread.scrollTop = thread.scrollHeight;
    if (window.lucide) lucide.createIcons();
}

function appendBotChatMessage(data) {
    const thread = document.getElementById("ai-chat-thread");
    if (!thread) return;

    const botBubble = document.createElement("div");
    botBubble.className = "chat-message bot-message";
    const isKn = data.is_kannada_input;
    const textEn = data.narrative_english || "";
    const textKn = data.narrative_kannada ? `ಕನ್ನಡ: ${data.narrative_kannada}` : "";
    const insightText = isKn ? data.companion_insight_kannada : data.companion_insight_english;
    const sqlQuery = data.generated_sql || "";

    botBubble.innerHTML = `
        <div class="message-avatar"><i data-lucide="shield"></i></div>
        <div class="message-body">
            <div class="message-sender">KSP Police Companion <span class="badge-tag">AI Officer</span></div>
            <div class="message-text">
                <p style="margin-bottom: 6px;">${textEn}</p>
                ${textKn ? `<p style="font-weight: 600; color: #1e1b4b; margin-bottom: 6px;">${textKn}</p>` : ''}
                ${insightText ? `<div class="companion-insight-badge">${insightText}</div>` : ''}
            </div>
            ${sqlQuery ? `<div class="chat-sql-snippet"><code>${sqlQuery}</code></div>` : ''}
        </div>
    `;
    thread.appendChild(botBubble);
    thread.scrollTop = thread.scrollHeight;
    if (window.lucide) lucide.createIcons();
}

function updateRightSideIntelligencePanel(data, questionText) {
    // 1. Query Tag
    const tagEl = document.getElementById("intel-query-tag");
    if (tagEl) tagEl.textContent = questionText;

    // 2. Statistics
    const stats = data.stats || {};
    const totalEl = document.getElementById("intel-total-crimes");
    const activeEl = document.getElementById("intel-active-crimes");
    const solvedEl = document.getElementById("intel-solved-crimes");
    const lossEl = document.getElementById("intel-total-loss");

    if (totalEl) totalEl.textContent = stats.total_crimes !== undefined ? stats.total_crimes : (data.result_count || 0);
    if (activeEl) activeEl.textContent = stats.active_cases !== undefined ? stats.active_cases : '--';
    if (solvedEl) solvedEl.textContent = stats.solved_cases !== undefined ? stats.solved_cases : '--';
    if (lossEl) lossEl.textContent = stats.total_loss !== undefined ? `₹${Math.round(stats.total_loss).toLocaleString()}` : '₹0';

    // 3. Location Breakdown List
    const locsList = document.getElementById("intel-locations-list");
    if (locsList) {
        locsList.innerHTML = "";
        const topLocs = stats.top_locations || [];
        if (topLocs.length > 0) {
            topLocs.forEach(loc => {
                const row = document.createElement("div");
                row.className = "loc-item-row";
                row.innerHTML = `
                    <span><i data-lucide="map-pin" style="width:14px; height:14px; margin-right:4px; inline-block;"></i> ${loc.location}</span>
                    <strong>${loc.count} cases</strong>
                `;
                locsList.appendChild(row);
            });
        } else {
            locsList.innerHTML = `<div class="intel-empty-note">No location breakdown available for this query.</div>`;
        }
    }

    // 4. Companion Tactical Hints
    const hintTextEl = document.getElementById("intel-hint-text");
    if (hintTextEl) {
        const hint = data.is_kannada_input ? (stats.tactical_hint_kannada || data.companion_insight_kannada) : (stats.tactical_hint_english || data.companion_insight_english);
        hintTextEl.textContent = hint || "Deploy night motorcycle patrols and monitor active MO patterns.";
    }

    const suspectsTags = document.getElementById("intel-suspects-tags");
    if (suspectsTags) {
        suspectsTags.innerHTML = "";
        const suspects = stats.suspects || [];
        if (suspects.length > 0) {
            suspects.forEach(s => {
                const span = document.createElement("span");
                span.className = "tag-pill suspect-lead";
                span.textContent = s;
                suspectsTags.appendChild(span);
            });
        } else {
            suspectsTags.innerHTML = `<span class="tag-pill">Unidentified Suspects</span>`;
        }
    }

    const moTags = document.getElementById("intel-mo-tags");
    if (moTags) {
        moTags.innerHTML = "";
        const mos = stats.mo_signatures || [];
        if (mos.length > 0) {
            mos.forEach(m => {
                const span = document.createElement("span");
                span.className = "tag-pill mo-lead";
                span.textContent = m;
                moTags.appendChild(span);
            });
        } else {
            moTags.innerHTML = `<span class="tag-pill">Standard MO Pattern</span>`;
        }
    }

    // 5. Follow-up Suggestions
    const suggBox = document.getElementById("ai-companion-suggestions");
    if (suggBox && data.suggested_followups) {
        suggBox.innerHTML = "";
        data.suggested_followups.forEach(sugg => {
            const btn = document.createElement("button");
            btn.className = "prompt-chip suggestion-followup-chip";
            btn.innerHTML = `<i data-lucide="sparkles"></i> ${sugg}`;
            btn.addEventListener("click", () => {
                sendAIQuery(sugg);
            });
            suggBox.appendChild(btn);
        });
    }

    if (window.lucide) lucide.createIcons();
}

function runAIQueryFromChip(text) {
    document.getElementById("ai-chat-input").value = text;
    sendAIQuery(text);
}

async function sendAIQuery(questionText) {
    if (!questionText || !questionText.trim()) return;
    const q = questionText.trim();
    
    // Clear input field
    document.getElementById("ai-chat-input").value = "";

    // 1. Append User Message Bubble to Thread
    appendUserChatMessage(q);

    try {
        const res = await fetch("/api/ai/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: q })
        });
        const data = await res.json();

        // 2. Append AI Bot Message Bubble to Thread
        appendBotChatMessage(data);

        // 3. Update Right-Side Crime & Suspect Intelligence Panel
        updateRightSideIntelligencePanel(data, q);

        // 4. Update Map markers strictly to matching query records
        if (data.records && data.records.length > 0) {
            masterCrimesData = data.records;
            renderMapMarkers(data.records);
            if (crimeMap && data.records[0].latitude && data.records[0].longitude) {
                crimeMap.flyTo([data.records[0].latitude, data.records[0].longitude], 12);
            }
        } else {
            masterCrimesData = [];
            renderMapMarkers([]);
        }
    } catch (e) {
        console.error("AI Query Error:", e);
    }
}

async function loadNetworkGraph() {
    const container = document.getElementById("criminal-network-vis");
    if (!container) return;

    try {
        const res = await fetch("/api/ai/network_graph?limit=60");
        const json = await res.json();
        const graphData = json.data;

        if (visNetworkInstance) visNetworkInstance.destroy();

        const nodes = new vis.DataSet(graphData.nodes);
        const edges = new vis.DataSet(graphData.edges);

        document.getElementById("net-nodes-cnt").textContent = graphData.nodes_count || nodes.length;
        document.getElementById("net-edges-cnt").textContent = graphData.edges_count || edges.length;

        const isKn = document.querySelector(".lang-btn.active")?.id === "btn-lang-kn";
        const insightEl = document.getElementById("graph-insight-text");
        if (insightEl) {
            insightEl.textContent = isKn ? graphData.companion_insight_kn : graphData.companion_insight_en;
        }

        const actionsBox = document.getElementById("graph-action-chips");
        if (actionsBox && graphData.suggested_actions) {
            actionsBox.innerHTML = "";
            graphData.suggested_actions.forEach(act => {
                const chip = document.createElement("button");
                chip.className = "prompt-chip suggestion-followup-chip";
                chip.textContent = act;
                chip.addEventListener("click", () => {
                    document.getElementById("ai-chat-input").value = act;
                    sendAIQuery(act);
                });
                actionsBox.appendChild(chip);
            });
        }

        const data = { nodes: nodes, edges: edges };
        const options = {
            nodes: { shape: 'dot', size: 18, font: { color: '#ffffff', size: 12, face: 'Poppins' } },
            edges: { color: { color: 'rgba(56, 189, 248, 0.3)' }, width: 1.5 },
            physics: { barnesHut: { gravitationalConstant: -3500 } }
        };

        visNetworkInstance = new vis.Network(container, data, options);

        visNetworkInstance.on("selectNode", function (params) {
            if (params.nodes.length > 0) {
                const nodeId = params.nodes[0];
                const nodeObj = nodes.get(nodeId);
                if (nodeObj) {
                    insightEl.innerHTML = `
                        <strong style="color: #38bdf8;">Selected Node: ${nodeObj.label}</strong><br>
                        <span>Type: ${nodeObj.type}</span><br>
                        <span>Details: ${nodeObj.title}</span><br>
                        <em style="color: #f59e0b;">Police Companion Note: Cross-referencing case records connected to node ${nodeObj.label}.</em>
                    `;
                }
            }
        });
    } catch (e) {
        console.error("Error rendering network graph:", e);
    }
}

function exportConversationPDF() {
    const threadEl = document.getElementById("ai-chat-thread");
    const messages = [];
    if (threadEl) {
        threadEl.querySelectorAll(".chat-message").forEach(msg => {
            const isUser = msg.classList.contains("user-message");
            const sender = isUser ? "Investigating Officer" : "KSP Police Companion AI";
            const textEl = msg.querySelector(".message-text");
            const text = textEl ? textEl.innerText : "";
            const sqlEl = msg.querySelector(".chat-sql-snippet");
            const sql = sqlEl ? sqlEl.innerText : "";
            messages.push({ isUser, sender, text, sql });
        });
    }

    const queryTag = document.getElementById("intel-query-tag")?.innerText || "Statewide Search";
    const totalCrimes = document.getElementById("intel-total-crimes")?.innerText || "0";
    const activeCrimes = document.getElementById("intel-active-crimes")?.innerText || "0";
    const solvedCrimes = document.getElementById("intel-solved-crimes")?.innerText || "0";
    const totalLoss = document.getElementById("intel-total-loss")?.innerText || "₹0";
    const hintText = document.getElementById("intel-hint-text")?.innerText || "No tactical hints logged.";
    
    const suspects = Array.from(document.querySelectorAll("#intel-suspects-tags .tag-pill")).map(t => t.innerText).join(", ");
    const moList = Array.from(document.querySelectorAll("#intel-mo-tags .tag-pill")).map(t => t.innerText).join(", ");

    const locations = [];
    document.querySelectorAll("#intel-locations-list .loc-item-row").forEach(row => {
        locations.push(row.innerText);
    });

    const printWin = window.open('', '_blank');
    if (!printWin) {
        alert("Popup blocked! Please allow popups for this site to view and download the PDF report.");
        return;
    }

    printWin.document.write(`
        <!DOCTYPE html>
        <html>
        <head>
            <title>KSP Police Intelligence Audit & Briefing Report</title>
            <style>
                body { font-family: 'Segoe UI', Arial, sans-serif; padding: 30px; color: #0f172a; line-height: 1.6; background: #fff; }
                .header { border-bottom: 3px solid #1e3a8a; padding-bottom: 12px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
                .header h1 { color: #1e3a8a; margin: 0; font-size: 22px; font-weight: 800; letter-spacing: 0.5px; }
                .header p { color: #64748b; margin: 4px 0 0 0; font-size: 13px; }
                .badge { background: #1e3a8a; color: #fff; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 700; text-transform: uppercase; }
                .grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 10px; margin-bottom: 20px; }
                .kpi-box { background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px; text-align: center; }
                .kpi-box .lbl { font-size: 11px; color: #64748b; font-weight: 600; text-transform: uppercase; }
                .kpi-box .val { font-size: 18px; color: #1e3a8a; font-weight: 800; margin-top: 4px; }
                .section { background: #fff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 16px; margin-bottom: 18px; }
                .section h3 { margin-top: 0; color: #1e3a8a; font-size: 15px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; font-weight: 700; }
                .msg-box { margin-bottom: 12px; padding: 12px; border-radius: 8px; font-size: 13px; }
                .msg-box.user { background: #eff6ff; border-left: 4px solid #2563eb; }
                .msg-box.bot { background: #f8fafc; border-left: 4px solid #059669; }
                .msg-sender { font-size: 11px; font-weight: 700; color: #475569; margin-bottom: 4px; }
                .sql-box { background: #0f172a; color: #38bdf8; font-family: monospace; padding: 8px 12px; border-radius: 6px; font-size: 11px; margin-top: 6px; word-break: break-all; }
                .hint-box { background: #fffbeb; border-left: 4px solid #d97706; padding: 12px; font-size: 13px; color: #78350f; border-radius: 6px; font-weight: 500; }
                .footer { margin-top: 30px; font-size: 11px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 12px; }
                ul { margin: 6px 0; padding-left: 20px; font-size: 13px; }
            </style>
        </head>
        <body>
            <div class="header">
                <div>
                    <h1>KARNATAKA STATE POLICE</h1>
                    <p>Official Crime Intelligence & Field Investigation Briefing Report</p>
                    <p><strong>Query Context:</strong> ${queryTag} | <strong>Generated:</strong> ${new Date().toLocaleString()}</p>
                </div>
                <span class="badge">CONFIDENTIAL</span>
            </div>

            <div class="grid">
                <div class="kpi-box"><div class="lbl">Total Crimes</div><div class="val">${totalCrimes}</div></div>
                <div class="kpi-box"><div class="lbl">Active / Open</div><div class="val" style="color:#dc2626;">${activeCrimes}</div></div>
                <div class="kpi-box"><div class="lbl">Solved / Closed</div><div class="val" style="color:#16a34a;">${solvedCrimes}</div></div>
                <div class="kpi-box"><div class="lbl">Financial Loss</div><div class="val">${totalLoss}</div></div>
            </div>

            <div class="section">
                <h3>1. Tactical Suspect Hints & Field Action Tips</h3>
                <div class="hint-box">${hintText}</div>
                <p style="font-size:12px; margin-top:8px; color:#475569;">
                    <strong>Known Suspect Leads:</strong> ${suspects || 'None'}<br>
                    <strong>Modus Operandi Tactics:</strong> ${moList || 'Standard MO'}
                </p>
            </div>

            ${locations.length > 0 ? `
            <div class="section">
                <h3>2. Crime Location Breakdown</h3>
                <ul>
                    ${locations.map(l => `<li>${l}</li>`).join('')}
                </ul>
            </div>
            ` : ''}

            <div class="section">
                <h3>3. Conversational AI Audit Trail (${messages.length} Messages)</h3>
                ${messages.map(m => `
                    <div class="msg-box ${m.isUser ? 'user' : 'bot'}">
                        <div class="msg-sender">${m.sender}</div>
                        <div>${m.text}</div>
                        ${m.sql ? `<div class="sql-box">${m.sql}</div>` : ''}
                    </div>
                `).join('')}
            </div>

            <div class="footer">
                Karnataka State Police Command Network - Field Report Logged - Confidential
            </div>

            <script>
                window.onload = function() { window.print(); }
            </script>
        </body>
        </html>
    `);
    printWin.document.close();
}

/* Global Multi-Field Search Engine */
function initGlobalSearch() {
    const input = document.getElementById("global-search-input");
    const suggestionsBox = document.getElementById("global-search-suggestions");
    const clearBtn = document.getElementById("clear-search-btn");
    if (!input) return;

    let debounceTimer;

    input.addEventListener("input", (e) => {
        const val = e.target.value.trim();
        if (val) clearBtn.classList.remove("hidden");
        else clearBtn.classList.add("hidden");

        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            if (val.length >= 2) {
                fetchGlobalSearchSuggestions(val);
            } else {
                suggestionsBox.classList.add("hidden");
            }
        }, 250);
    });

    clearBtn.addEventListener("click", () => {
        input.value = "";
        clearBtn.classList.add("hidden");
        suggestionsBox.classList.add("hidden");
    });

    document.addEventListener("click", (e) => {
        if (!e.target.closest(".global-search-wrapper")) {
            suggestionsBox.classList.add("hidden");
        }
    });
}

async function fetchGlobalSearchSuggestions(queryStr) {
    const suggestionsBox = document.getElementById("global-search-suggestions");
    try {
        const res = await fetch(`/api/crimes?q=${encodeURIComponent(queryStr)}&limit=6`);
        const json = await res.json();
        const matches = json.data || [];

        suggestionsBox.innerHTML = "";
        if (matches.length === 0) {
            suggestionsBox.innerHTML = `<div class="suggestion-item"><span class="sugg-sub">No matching database records found</span></div>`;
        } else {
            matches.forEach(item => {
                const div = document.createElement("div");
                div.className = "suggestion-item";
                div.innerHTML = `
                    <div class="sugg-main">
                        <span class="sugg-title">${item.crime_type} (${item.case_id})</span>
                        <span class="sugg-sub">${item.division} | ${item.suspect_name || item.station_id}</span>
                    </div>
                    <span class="sugg-badge">${item.status}</span>
                `;
                div.addEventListener("click", () => {
                    suggestionsBox.classList.add("hidden");
                    openCriminalProfileModal(item);
                    if (crimeMap && item.latitude && item.longitude) {
                        crimeMap.flyTo([item.latitude, item.longitude], 14, { animate: true, duration: 1.2 });
                    }
                    const resInput = document.getElementById("res-search-input");
                    if (resInput) {
                        resInput.value = item.case_id;
                        lookupCaseForResolution();
                    }
                });
                suggestionsBox.appendChild(div);
            });
        }
        suggestionsBox.classList.remove("hidden");
    } catch (e) {
        console.error("Global search error:", e);
    }
}

/* Mouse Interactions (Disabled) */
function initMouseInteractions() {}

/* Criminal Profile Modal System */
function initProfileModal() {
    const closeBtn = document.getElementById("profile-modal-close");
    const modal = document.getElementById("criminal-profile-modal");
    const dispatchBtn = document.getElementById("alert-police-dispatch-btn");

    if (closeBtn && modal) {
        closeBtn.addEventListener("click", () => modal.classList.add("hidden"));
    }
    if (dispatchBtn) {
        dispatchBtn.addEventListener("click", () => {
            alert("EMERGENCY POLICE DISPATCH TRIGGERED! Nearest mobile patrol unit dispatched to suspect location.");
            modal.classList.add("hidden");
        });
    }
}

function openCriminalProfileModal(crimeObj) {
    const modal = document.getElementById("criminal-profile-modal");
    if (!modal || !crimeObj) return;

    document.getElementById("prof-suspect-name").textContent = crimeObj.suspect_name || `Accused in ${crimeObj.case_id}`;
    document.getElementById("prof-crime-subtitle").textContent = `${crimeObj.crime_type} (${crimeObj.mo_signature || 'Incident Record'})`;
    document.getElementById("prof-priority-tag").textContent = `${crimeObj.severity || 'High'} Priority`;
    document.getElementById("prof-status-tag").textContent = crimeObj.status || 'Wanted';
    
    document.getElementById("prof-bio-desc").textContent = crimeObj.resolution_notes || crimeObj.description || "Suspect associated with reported criminal incidents under active police investigation.";
    document.getElementById("prof-div").textContent = `${crimeObj.division} (${crimeObj.station_id})`;
    document.getElementById("prof-case-id").textContent = crimeObj.case_id;
    document.getElementById("prof-time").textContent = crimeObj.date_time;

    modal.classList.remove("hidden");
}

function openCriminalProfileModalByCase(caseId) {
    const match = masterCrimesData.find(c => c.case_id === caseId);
    if (match) {
        openCriminalProfileModal(match);
    } else {
        fetch(`/api/crimes?q=${encodeURIComponent(caseId)}`).then(r => r.json()).then(res => {
            if (res.data && res.data[0]) openCriminalProfileModal(res.data[0]);
        });
    }
}
