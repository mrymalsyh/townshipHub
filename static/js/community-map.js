(function () {
  var reports = JSON.parse(document.getElementById("pins-data").textContent);
  var zones = JSON.parse(document.getElementById("quick-zones-data").textContent);
  var routeLocations = JSON.parse(document.getElementById("route-locations-data").textContent);
  var map = L.map("map").setView([3.2160, 101.5108], 16);
  L.DomEvent.disableClickPropagation(document.querySelector(".map-controls"));
  L.DomEvent.disableScrollPropagation(document.querySelector(".map-controls"));
  L.tileLayer("https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, tiles style by <a href="https://www.hotosm.org/">Humanitarian OpenStreetMap Team</a>, hosted by <a href="https://www.openstreetmap.fr/">OpenStreetMap France</a>'
  }).addTo(map);

  var drawer = document.getElementById("hotspot-drawer");
  var drawerContent = document.getElementById("hotspot-content");
  var activeFilter = "all";
  var mapMode = "standard";
  var nearbyRadius = null;
  var userLocation = null;
  var radiusCircle = null;
  var routeLayer = null;
  var clusterGroup = L.markerClusterGroup({
    maxClusterRadius: 55,
    showCoverageOnHover: false,
    spiderfyOnMaxZoom: true,
    zoomToBoundsOnClick: true,
    iconCreateFunction: clusterIcon
  });
  var heatGroup = L.layerGroup();
  var overlayGroup = L.layerGroup();
  map.addLayer(clusterGroup);

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (character) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[character];
    });
  }

  function markerIcon(report, dimmed) {
    var urgent = report.urgency === "high";
    return L.divIcon({
      className: "report-pin-wrap" + (dimmed ? " outside-radius" : ""),
      iconSize: [32, 32],
      iconAnchor: [16, 16],
      html: '<span class="report-pin ' + (urgent ? "urgent" : "low") + '">1</span>'
    });
  }

  function clusterIcon(cluster) {
    var childReports = cluster.getAllChildMarkers().map(function (marker) { return marker.reportData; });
    var count = childReports.length;
    var urgent = childReports.some(function (report) { return report.urgency === "high"; });
    var tone = urgent || count >= 9 ? "high" : count >= 4 ? "medium" : "low";
    return L.divIcon({
      className: "report-cluster-wrap",
      iconSize: [48, 48],
      iconAnchor: [24, 24],
      html: '<span class="report-cluster ' + tone + '">' + count + '</span>'
    });
  }

  function showSummary(items, title) {
    if (!items.length) {
      drawerContent.innerHTML = "<h2>" + escapeHtml(title) + "</h2>";
      drawer.hidden = false;
      return;
    }
    var categories = {};
    var statuses = {};
    items.forEach(function (report) {
      categories[report.category_label] = (categories[report.category_label] || 0) + 1;
      statuses[report.status_label] = (statuses[report.status_label] || 0) + 1;
    });
    var categoryText = Object.keys(categories).map(function (label) {
      return categories[label] + " " + escapeHtml(label);
    }).join(", ");
    var statusText = Object.keys(statuses).map(function (label) {
      return statuses[label] + " " + escapeHtml(label);
    }).join(", ");
    var routes = items.filter(function (report) { return report.route; });
    var csrfToken = document.querySelector("#map-vote-csrf input[name=csrfmiddlewaretoken]").value;
    var csrfInput = '<input type="hidden" name="csrfmiddlewaretoken" value="' +
      escapeHtml(csrfToken) + '">';
    var links = items.map(function (report) {
      var item = '<li><a href="' + escapeHtml(report.url) + '">' + escapeHtml(report.title) +
        '</a><span class="small muted"> · ' + escapeHtml(report.status_label) +
        (report.spot ? ' · ' + escapeHtml(report.spot) : '') + '</span>';
      if (report.can_vote) {
        var voteStatus = report.user_vote === null
          ? ""
          : '<p class="small muted">Your current answer: ' +
            (report.user_vote ? "still broken" : "looks fixed") + '. You can change it.</p>';
        item += voteStatus + '<form class="map-vote-form" method="post" action="' +
          escapeHtml(report.vote_url) + '">' + csrfInput +
          '<button class="btn small warn" type="submit" name="answer" value="broken">Still broken</button> ' +
          '<button class="btn small ghost" type="submit" name="answer" value="fixed">Looks fixed</button></form>';
      } else {
        item += '<p class="small muted">Your report — residents can confirm other residents’ reports.</p>';
      }
      return item + '</li>';
    }).join("");
    var routeAdvice = routes.length
      ? '<div class="hotspot-routes"><b>Safe detour advice</b><ul>' + routes.map(function (report) {
          return '<li><a href="' + escapeHtml(report.url) + '">' + escapeHtml(report.name) + '</a>: ' +
            escapeHtml(report.route) + '</li>';
        }).join("") + '</ul></div>'
      : "";
    var locationNames = Array.from(new Set(items.map(function (report) { return report.name; })));
    var summaryTitle = title || (items.length + " Reports in " +
      (locationNames.length === 1 ? locationNames[0] : locationNames.length + " locations"));
    drawerContent.innerHTML = '<h2>' + escapeHtml(summaryTitle) +
      '</h2><p><b>Primary types:</b> ' + categoryText + '</p><p><b>Top status:</b> ' + statusText +
      '</p>' + routeAdvice + '<details class="hotspot-report-list"><summary>Review all ' + items.length +
      ' reports here</summary><ul>' + links + '</ul></details>';
    drawer.hidden = false;
  }

  function currentReports() {
    var filtered = reports.filter(function (report) {
      if (activeFilter === "active" && report.status === "resolved") return false;
      if (activeFilter === "maintenance" && report.status !== "in_progress") return false;
      if (activeFilter === "detours" && (report.status === "resolved" || !report.route)) return false;
      if (mapMode === "pedestrian" && (report.status === "resolved" ||
          (report.category !== "pathway" && report.category !== "safety" && !report.route))) return false;
      if (mapMode === "night" && (report.status === "resolved" || report.category !== "lighting")) return false;
      return true;
    });
    return filtered;
  }

  function isOutsideRadius(report) {
    return nearbyRadius !== null && userLocation !== null &&
      map.distance(userLocation, L.latLng(report.lat, report.lng)) > nearbyRadius;
  }

  function refreshLayers() {
    clusterGroup.clearLayers();
    heatGroup.clearLayers();
    overlayGroup.clearLayers();
    var visibleReports = currentReports();

    if (mapMode === "heat") {
      var densityCells = {};
      visibleReports.forEach(function (report) {
        var key = Math.floor(report.lat * 1000) + ":" + Math.floor(report.lng * 1000);
        if (!densityCells[key]) densityCells[key] = {count: 0, urgent: false};
        densityCells[key].count += 1;
        densityCells[key].urgent = densityCells[key].urgent || report.urgency === "high";
      });
      visibleReports.forEach(function (report) {
        var latitudeCell = Math.floor(report.lat * 1000);
        var longitudeCell = Math.floor(report.lng * 1000);
        var nearbyCount = 0;
        var urgent = false;
        for (var row = -1; row <= 1; row += 1) {
          for (var column = -1; column <= 1; column += 1) {
            var cell = densityCells[(latitudeCell + row) + ":" + (longitudeCell + column)];
            if (cell) {
              nearbyCount += cell.count;
              urgent = urgent || cell.urgent;
            }
          }
        }
        var color = urgent || nearbyCount >= 9 ? "#b42318" :
          (nearbyCount >= 4 ? "#c05b00" : "#18794e");
        L.circle([report.lat, report.lng], {
          radius: 85,
          color: color,
          weight: 1,
          fillColor: color,
          fillOpacity: isOutsideRadius(report) ? .025 : .14,
          opacity: isOutsideRadius(report) ? .05 : .22
        }).bindTooltip(nearbyCount + " report(s) in nearby map cells").addTo(heatGroup);
      });
      heatGroup.addTo(map);
    } else if (mapMode === "night") {
      visibleReports.forEach(function (report) {
        L.circleMarker([report.lat, report.lng], {
          radius: 13,
          color: "#8a4b00",
          weight: 2,
          fillColor: report.urgency === "high" ? "#b42318" : "#f5c518",
          fillOpacity: isOutsideRadius(report) ? .15 : .9,
          opacity: isOutsideRadius(report) ? .15 : 1
        }).bindTooltip("Reported streetlight issue: " + escapeHtml(report.title))
          .on("click", function () { showSummary([report], report.title); })
          .addTo(overlayGroup);
      });
      overlayGroup.addTo(map);
    } else {
      visibleReports.forEach(function (report) {
        var marker = L.marker([report.lat, report.lng], {
          icon: markerIcon(report, isOutsideRadius(report))
        });
        marker.reportData = report;
        marker.on("click", function () { showSummary([report], report.title); });
        clusterGroup.addLayer(marker);
      });
      clusterGroup.addTo(map);
    }
    if (radiusCircle) radiusCircle.bringToFront();
  }

  clusterGroup.on("clusterclick", function (event) {
    var items = event.layer.getAllChildMarkers().map(function (marker) { return marker.reportData; });
    showSummary(items);
  });

  function selectFilter(filter) {
    activeFilter = filter;
    document.querySelectorAll("[data-map-filter]").forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.dataset.mapFilter === filter));
    });
    drawer.hidden = true;
    refreshLayers();
  }

  document.querySelectorAll("[data-map-filter]").forEach(function (button) {
    button.addEventListener("click", function () { selectFilter(button.dataset.mapFilter); });
  });

  var modeMessages = {
    standard: "Report clusters and individual public reports.",
    heat: "Glows show report density around mapped report locations; they are indicative, not exact hazard boundaries.",
    night: "Shows reported, unresolved streetlight faults only; it does not certify which paths are well lit.",
    pedestrian: "Highlights active pathway and safety reports, with any management detour text. No verified path, ramp or step-free data is recorded."
  };
  document.querySelectorAll("[data-map-mode]").forEach(function (button) {
    button.addEventListener("click", function () {
      mapMode = button.dataset.mapMode;
      document.querySelectorAll("[data-map-mode]").forEach(function (item) {
        item.setAttribute("aria-pressed", String(item === button));
      });
      document.getElementById("mode-status").textContent = modeMessages[mapMode];
      drawer.hidden = true;
      refreshLayers();
    });
  });
  document.getElementById("mode-status").textContent = modeMessages.standard;

  document.querySelectorAll("[data-zone]").forEach(function (button) {
    button.addEventListener("click", function () {
      var zone = zones.find(function (item) { return item.key === button.dataset.zone; });
      if (!zone || !zone.available) return;
      var point = L.latLng(zone.lat, zone.lng);
      map.flyTo(point, 18, {duration: .8});
      var nearbyReports = reports.filter(function (report) {
        return map.distance(point, L.latLng(report.lat, report.lng)) <= 150;
      });
      var facilitySummary = zone.facilities.map(function (facility) {
        var maintenance = facility.maintenance.length
          ? '<br><span class="small muted">' + facility.maintenance.map(escapeHtml).join("; ") + '</span>'
          : "";
        return '<li><a href="' + escapeHtml(facility.url) + '">' + escapeHtml(facility.name) +
          '</a> — ' + escapeHtml(facility.status) + '; ' + facility.booking_count +
          ' booking(s) today' + maintenance + '</li>';
      }).join("");
      showSummary(nearbyReports, zone.location_name);
      if (zone.facilities.length) {
        drawerContent.insertAdjacentHTML("beforeend",
          '<section class="zone-facility-summary"><h3>Facility status nearby</h3><ul>' +
          facilitySummary + '</ul></section>');
      }
      if (!nearbyReports.length && !zone.facilities.length) {
        drawerContent.insertAdjacentHTML("beforeend", "<p>No reports or mapped facilities are recorded for this zone.</p>");
      }
    });
  });
  document.querySelectorAll("[data-zone-count]").forEach(function (badge) {
    var zone = zones.find(function (item) { return item.key === badge.dataset.zoneCount; });
    if (!zone || !zone.available) return;
    var center = L.latLng(zone.lat, zone.lng);
    var count = reports.filter(function (report) {
      return map.distance(center, L.latLng(report.lat, report.lng)) <= 150 &&
        report.status !== "resolved";
    }).length;
    badge.textContent = count;
    badge.setAttribute("aria-label", count + " active report(s)");
  });

  var radiusStatus = document.getElementById("location-status");
  function applyRadius(radius) {
    nearbyRadius = radius === "all" ? null : Number(radius);
    document.querySelectorAll("[data-radius]").forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.dataset.radius === radius));
    });
    if (radius === "all") {
      if (radiusCircle) map.removeLayer(radiusCircle);
      radiusCircle = null;
      userLocation = null;
      radiusStatus.textContent = "Showing the whole township.";
      refreshLayers();
      return;
    }
    if (radiusCircle) map.removeLayer(radiusCircle);
    radiusCircle = null;
    if (!navigator.geolocation) {
      nearbyRadius = null;
      radiusStatus.textContent = "This browser does not support location. Whole township remains visible.";
      return;
    }
    var requestedRadius = nearbyRadius;
    radiusStatus.textContent = "Requesting your location…";
    navigator.geolocation.getCurrentPosition(function (position) {
      userLocation = L.latLng(position.coords.latitude, position.coords.longitude);
      nearbyRadius = requestedRadius;
      radiusCircle = L.circle(userLocation, {
        radius: requestedRadius,
        color: "#70020f",
        weight: 2,
        opacity: .7,
        fillColor: "#fedee1",
        fillOpacity: .16
      }).addTo(map);
      map.fitBounds(radiusCircle.getBounds(), {padding: [25, 25]});
      radiusStatus.textContent = "Showing reports within " +
        (requestedRadius === 500 ? "500 m" : "1 km") + " of your location; reports outside are dimmed.";
      refreshLayers();
    }, function (error) {
      nearbyRadius = null;
      userLocation = null;
      document.querySelector('[data-radius="all"]').setAttribute("aria-pressed", "true");
      document.querySelectorAll("[data-radius]").forEach(function (button) {
        if (button.dataset.radius !== "all") button.setAttribute("aria-pressed", "false");
      });
      var reason = error.code === error.PERMISSION_DENIED
        ? "Location permission was denied."
        : "Your location could not be determined.";
      radiusStatus.textContent = reason + " Whole township remains visible.";
      refreshLayers();
    }, {enableHighAccuracy: false, timeout: 10000, maximumAge: 60000});
  }
  document.querySelectorAll("[data-radius]").forEach(function (button) {
    button.addEventListener("click", function () { applyRadius(button.dataset.radius); });
  });

  var routeForm = document.getElementById("route-form");
  var routeResult = document.getElementById("route-result");
  var routeById = {};
  routeLocations.forEach(function (location) { routeById[String(location.id)] = location; });
  routeForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var start = routeById[document.getElementById("route-start").value];
    var end = routeById[document.getElementById("route-end").value];
    if (!start || !end || start.id === end.id) {
      routeResult.textContent = "Choose two different mapped locations.";
      return;
    }
    routeResult.textContent = "Checking walking routes and active public hazards…";
    var coordinates = start.lng + "," + start.lat + ";" + end.lng + "," + end.lat;
    var url = "https://routing.openstreetmap.de/routed-foot/route/v1/driving/" + coordinates +
      "?alternatives=3&overview=full&geometries=geojson&steps=false";
    fetch(url).then(function (response) {
      if (!response.ok) throw new Error("Walking route service returned HTTP " + response.status + ".");
      return response.json();
    }).then(function (data) {
      if (data.code !== "Ok" || !data.routes || !data.routes.length) {
        throw new Error("No walking route was found between those mapped locations.");
      }
      var candidates = data.routes.map(function (route) {
        var hazards = reports.filter(function (report) {
          if (report.status === "resolved") return false;
          if (report.category !== "pathway" && report.category !== "safety" &&
              report.category !== "drainage" && report.urgency !== "high") return false;
          return routeNearReport(route.geometry.coordinates, report, 35);
        });
        return {route: route, hazards: hazards};
      });
      candidates.sort(function (first, second) {
        return first.hazards.length - second.hazards.length ||
          first.route.duration - second.route.duration;
      });
      var best = candidates[0];
      if (routeLayer) map.removeLayer(routeLayer);
      routeLayer = L.geoJSON(best.route.geometry, {
        style: {color: best.hazards.length ? "#c05b00" : "#18794e", weight: 6, opacity: .85}
      }).addTo(map);
      map.fitBounds(routeLayer.getBounds(), {padding: [40, 40]});
      var minutes = Math.max(1, Math.round(best.route.duration / 60));
      if (best.hazards.length) {
        var advice = best.hazards.map(function (report) {
          return '<li><a href="' + escapeHtml(report.url) + '">' + escapeHtml(report.title) +
            '</a>' + (report.route ? ': ' + escapeHtml(report.route) : "") + '</li>';
        }).join("");
        routeResult.innerHTML = '<b>Closest available route still passes near ' +
          best.hazards.length + ' active hazard(s)</b> · about ' + minutes +
          ' min. Use caution and follow posted management advice.<ul>' + advice + '</ul>';
      } else {
        routeResult.innerHTML = '<b>Suggested walking route</b> · about ' + minutes +
          ' min. No active mapped hazards were found within 35 m of this route.';
      }
      routeResult.insertAdjacentHTML("beforeend",
        '<p class="small muted">Routing by the OpenStreetMap community service. Route and hazard data may be incomplete.</p>');
    }).catch(function (error) {
      routeResult.textContent = error.message + " Try again later or check management detour notices.";
    });
  });

  function routeNearReport(coordinates, report, limitMeters) {
    var latScale = 111320;
    var lngScale = 111320 * Math.cos(report.lat * Math.PI / 180);
    var px = report.lng * lngScale;
    var py = report.lat * latScale;
    for (var index = 1; index < coordinates.length; index += 1) {
      var firstX = coordinates[index - 1][0] * lngScale;
      var firstY = coordinates[index - 1][1] * latScale;
      var secondX = coordinates[index][0] * lngScale;
      var secondY = coordinates[index][1] * latScale;
      var deltaX = secondX - firstX;
      var deltaY = secondY - firstY;
      var lengthSquared = deltaX * deltaX + deltaY * deltaY;
      var amount = lengthSquared
        ? Math.max(0, Math.min(1, ((px - firstX) * deltaX + (py - firstY) * deltaY) / lengthSquared))
        : 0;
      var distanceX = px - (firstX + amount * deltaX);
      var distanceY = py - (firstY + amount * deltaY);
      if (Math.sqrt(distanceX * distanceX + distanceY * distanceY) <= limitMeters) return true;
    }
    if (coordinates.length === 1) {
      return map.distance([coordinates[0][1], coordinates[0][0]], [report.lat, report.lng]) <= limitMeters;
    }
    return false;
  }

  document.querySelectorAll(".map-announcements-list a[data-alert-lat]").forEach(function (link) {
    link.addEventListener("click", function (event) {
      event.preventDefault();
      var lat = Number(link.dataset.alertLat);
      var lng = Number(link.dataset.alertLng);
      map.flyTo([lat, lng], 18, {duration: .8});
      var nearbyReports = reports.filter(function (report) {
        return map.distance([lat, lng], [report.lat, report.lng]) <= 100;
      });
      showSummary(nearbyReports, "Township alert");
      drawerContent.insertAdjacentHTML("afterbegin", '<p>' + escapeHtml(link.innerText) +
        '</p><p><a href="' + escapeHtml(link.dataset.alertUrl) + '">' +
        escapeHtml(link.dataset.alertTarget) + '</a></p>');
    });
  });

  document.getElementById("hotspot-close").addEventListener("click", function () {
    drawer.hidden = true;
  });

  var bounds = reports.map(function (report) { return [report.lat, report.lng]; });
  if (bounds.length > 1) map.fitBounds(bounds, {padding: [40, 40], maxZoom: 17});
  else if (bounds.length === 1) map.setView(bounds[0], 18);
  var announcementTrack = document.querySelector(".map-announcements-track");
  if (announcementTrack) {
    if (announcementTrack.querySelector("a")) {
      var copy = announcementTrack.cloneNode(true);
      copy.setAttribute("aria-hidden", "true");
      copy.querySelectorAll("a").forEach(function (link) { link.tabIndex = -1; });
      announcementTrack.parentNode.appendChild(copy);
    } else {
      announcementTrack.classList.add("static");
    }
  }
  refreshLayers();
})();
