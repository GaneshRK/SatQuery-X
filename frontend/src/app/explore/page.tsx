"use client";

import { useState } from "react";
import AppShell from "../../components/AppShell";
import SectionTitle from "../../components/SectionTitle";
import MapPanel from "../../components/MapPanel";

export default function ExploreMapPage() {
  const [date, setDate] = useState("2026");
  const [selectedLocation, setSelectedLocation] = useState("Coimbatore, Tamil Nadu");

  const layersList = [
    "Sentinel-1 (SAR)",
    "Sentinel-2 (Optical)",
    "Landsat 8/9",
    "NDVI (Vegetation Index)",
    "Land Use / Land Cover",
    "Water Bodies",
    "Urban Areas",
    "Administrative Boundaries",
  ];

  return (
    <AppShell>
      <div className="page">
        <SectionTitle
          title="Explore Map"
          subtitle="Explore multi-spectral satellite data layers and planetary areas of interest."
        />

        <div className="map-page panel">
          <div className="map-toolbar">
            <input
              placeholder="Search a location..."
              value={selectedLocation}
              onChange={(e) => setSelectedLocation(e.target.value)}
            />
            <div className="layers">
              {layersList.map((x, i) => (
                <label key={x}>
                  <input type="checkbox" defaultChecked={i < 4} />
                  {x}
                </label>
              ))}
            </div>
          </div>

          <MapPanel height={600} label={selectedLocation} />

          <div className="timeline">
            <span>Jan 2020</span>
            <input
              type="range"
              min="2020"
              max="2026"
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
            <span>Selected: {date} (Current: Sep 2026)</span>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
