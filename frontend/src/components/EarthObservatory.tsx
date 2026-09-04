'use client';

import React, { useState, useEffect, useRef } from 'react';
import * as maplibregl from 'maplibre-gl';
import type { Map as MapLibreMap } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {
  Globe,
  Search,
  Compass,
  Layers,
  Sparkles,
  Maximize2,
  Minimize2,
  Calendar,
  Cloud,
  Satellite,
  Navigation,
  Eye,
  AlertTriangle,
  RotateCw,
} from 'lucide-react';
import {
  AOIData,
  AOITimelineResponse,
  ChangeEventData,
  createAOI,
  getAOITimeline,
  listChangeEvents,
  runChangeAnalysis,
} from '@/services/satellite';
import { TimelineSlider } from './TimelineSlider';

interface EarthObservatoryProps {
  onSelectAOI?: (aoi: AOIData) => void;
  onAskAI?: (prompt: string) => void;
}

const ORBITAL_TARGETS = [
  {
    name: 'Chennai Metropolitan Region',
    country: 'India',
    state: 'Tamil Nadu',
    coords: [80.2707, 13.0827] as [number, number],
    bbox: [80.15, 12.95, 80.35, 13.15],
    zoom: 11.5,
    pitch: 45,
    description: 'Rapid urban expansion, coastal infrastructure, and IT corridor growth (2016–2026).',
    category: 'URBAN_EXPANSION',
  },
  {
    name: 'Pollachi Agricultural Belt',
    country: 'India',
    state: 'Tamil Nadu',
    coords: [77.0064, 10.6582] as [number, number],
    bbox: [76.92, 10.58, 77.08, 10.72],
    zoom: 12.0,
    pitch: 40,
    description: 'Coconut plantations, agro-forestry, and Western Ghats seasonal canopy shifts.',
    category: 'VEGETATION_CHANGE',
  },
  {
    name: 'Kaziranga & Brahmaputra Basin',
    country: 'India',
    state: 'Assam',
    coords: [93.1711, 26.5775] as [number, number],
    bbox: [93.05, 26.50, 93.30, 26.65],
    zoom: 11.0,
    pitch: 50,
    description: 'Brahmaputra monsoon river dynamics, sandbar migration, and wildlife corridor floods.',
    category: 'WATER_DYNAMICS',
  },
  {
    name: 'Bengaluru IT Corridor',
    country: 'India',
    state: 'Karnataka',
    coords: [77.6974, 12.9352] as [number, number],
    bbox: [77.60, 12.85, 77.78, 13.02],
    zoom: 12.0,
    pitch: 42,
    description: 'Decadal peri-urban growth, lake encroachment, and tech infrastructure development.',
    category: 'URBAN_EXPANSION',
  },
  {
    name: 'Sundarbans Mangrove Delta',
    country: 'India / Bangladesh',
    state: 'West Bengal',
    coords: [88.8532, 21.9497] as [number, number],
    bbox: [88.70, 21.80, 89.00, 22.10],
    zoom: 11.0,
    pitch: 35,
    description: 'Tidal mangrove forest fluctuations, cyclone recovery, and estuarine sediment channels.',
    category: 'ENVIRONMENTAL',
  },
];

export const EarthObservatory: React.FC<EarthObservatoryProps> = ({
  onSelectAOI,
  onAskAI,
}) => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [activeTarget, setActiveTarget] = useState(ORBITAL_TARGETS[0]);
  const [cameraAltitude, setCameraAltitude] = useState<string>('HIGH ORBIT (8,500 km)');
  const [timeline, setTimeline] = useState<AOITimelineResponse | null>(null);
  const [selectedObsIndex, setSelectedObsIndex] = useState(0);
  const [changeEvents, setChangeEvents] = useState<ChangeEventData[]>([]);
  const [selectedChangeEvent, setSelectedChangeEvent] = useState<ChangeEventData | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [compareMode, setCompareMode] = useState(false);
  const [compareIndices, setCompareIndices] = useState<{ before: number; after: number }>({ before: 0, after: 0 });
  const [rotationActive, setRotationActive] = useState(false);
  const rotationTimerRef = useRef<number | null>(null);

  // Initialize MapLibre 3D Earth Globe
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    // High orbital initial position
    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {
          'esri-satellite': {
            type: 'raster',
            tiles: [
              'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            ],
            tileSize: 256,
            attribution: 'Esri, Maxar, Earthstar Geographics, CNES/Airbus DS',
          },
        },
        layers: [
          {
            id: 'background',
            type: 'background',
            paint: {
              'background-color': '#02040a',
            },
          },
          {
            id: 'satellite-global',
            type: 'raster',
            source: 'esri-satellite',
            minzoom: 0,
            maxzoom: 19,
          },
        ],
      },
      center: [78.9629, 20.5937], // Centered above Indian subcontinent from orbit
      zoom: 2.2,
      pitch: 35,
      bearing: 0,
      attributionControl: false,
    });

    // Try setting 3D globe projection if supported by maplibre version
    try {
      if (typeof (map as any).setProjection === 'function') {
        (map as any).setProjection({ type: 'globe' });
      }
    } catch (e) {
      console.log('Globe projection fallback to spherical web-mercator');
    }

    map.on('move', () => {
      const z = map.getZoom();
      if (z <= 3) {
        setCameraAltitude('HIGH ORBIT (>10,000 km)');
      } else if (z <= 6) {
        setCameraAltitude('CONTINENTAL ORBIT (2,500 km)');
      } else if (z <= 9) {
        setCameraAltitude('REGIONAL ALTITUDE (600 km)');
      } else if (z <= 12) {
        setCameraAltitude('AOI SATELLITE PASS (250 km)');
      } else {
        setCameraAltitude('HIGH-RES SATELLITE TILE (100 km)');
      }
    });

    mapRef.current = map;

    // Fetch existing global change events
    listChangeEvents()
      .then((res) => {
        setChangeEvents(res.events || []);
      })
      .catch((err) => console.error('Failed to list change events:', err));

    return () => {
      if (rotationTimerRef.current) cancelAnimationFrame(rotationTimerRef.current);
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Multi-phase orbital camera flight hierarchy: ORBIT -> SUBCONTINENT -> REGION -> AOI
  const executeOrbitalDescent = (target: typeof ORBITAL_TARGETS[0]) => {
    const map = mapRef.current;
    if (!map) return;

    setActiveTarget(target);
    setRotationActive(false);

    // Phase 1: Ascend slightly or rotate view towards subcontinent
    map.flyTo({
      center: target.coords,
      zoom: 4.5,
      pitch: 45,
      bearing: 15,
      duration: 2000,
      essential: true,
    });

    // Phase 2: Smooth atmospheric descent into target state / region
    setTimeout(() => {
      if (!mapRef.current) return;
      mapRef.current.flyTo({
        center: target.coords,
        zoom: 8.0,
        pitch: 35,
        bearing: 0,
        duration: 1800,
        essential: true,
      });
    }, 2100);

    // Phase 3: Final lock onto real satellite observation bounds
    setTimeout(() => {
      if (!mapRef.current) return;
      mapRef.current.flyTo({
        center: target.coords,
        zoom: target.zoom,
        pitch: target.pitch,
        bearing: 0,
        duration: 1600,
        essential: true,
      });

      // Query real Copernicus STAC catalogue and index timeline for target AOI
      createAOI({
        name: target.name,
        description: target.description,
        bbox: target.bbox,
      })
        .then((res) => {
          if (onSelectAOI) onSelectAOI(res.aoi);
          return getAOITimeline(res.aoi.id);
        })
        .then((tl) => {
          setTimeline(tl);
          setSelectedObsIndex(tl.observations.length > 0 ? tl.observations.length - 1 : 0);
        })
        .catch((err) => console.error('AOI timeline sync error:', err));
    }, 4000);
  };

  // Trigger default target descent on mount after initial delay
  useEffect(() => {
    const timer = setTimeout(() => {
      executeOrbitalDescent(ORBITAL_TARGETS[0]);
    }, 800);
    return () => clearTimeout(timer);
  }, []);

  // Handle location search form submission
  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    const queryLower = searchQuery.toLowerCase();
    const matched = ORBITAL_TARGETS.find(
      (t) =>
        t.name.toLowerCase().includes(queryLower) ||
        t.state.toLowerCase().includes(queryLower) ||
        t.country.toLowerCase().includes(queryLower)
    );

    if (matched) {
      executeOrbitalDescent(matched);
    } else {
      // Default to Chennai or prompt
      executeOrbitalDescent({
        name: searchQuery,
        country: 'Earth Observation Target',
        state: 'Geospatial Sector',
        coords: [80.25, 13.05],
        bbox: [80.15, 12.95, 80.35, 13.15],
        zoom: 11.5,
        pitch: 45,
        description: `Natural language Earth search target: ${searchQuery}`,
        category: 'CUSTOM_SEARCH',
      });
    }
  };

  // Run Bi-Temporal Change Detection
  const handleRunChangeDetection = async () => {
    if (!timeline) return;
    setIsAnalyzing(true);
    try {
      const event = await runChangeAnalysis({
        aoi_id: timeline.aoi_id,
        change_type: 'URBAN_EXPANSION',
      });
      setSelectedChangeEvent(event);
      setChangeEvents((prev) => [event, ...prev]);

      // Render detected change polygon on map
      const map = mapRef.current;
      if (map && event.change_polygon) {
        if (map.getSource('change-event-source')) {
          (map.getSource('change-event-source') as any).setData(event.change_polygon);
        } else {
          map.addSource('change-event-source', {
            type: 'geojson',
            data: event.change_polygon,
          });
          map.addLayer({
            id: 'change-event-fill',
            type: 'fill',
            source: 'change-event-source',
            paint: {
              'fill-color': '#f43f5e',
              'fill-opacity': 0.45,
            },
          });
          map.addLayer({
            id: 'change-event-line',
            type: 'line',
            source: 'change-event-source',
            paint: {
              'line-color': '#ff2056',
              'line-width': 2.5,
            },
          });
        }
      }
    } catch (err) {
      console.error('Change detection failed:', err);
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Handle Before/After Compare trigger
  const handleCompare = (beforeIdx: number, afterIdx: number) => {
    setCompareMode(!compareMode);
    setCompareIndices({ before: beforeIdx, after: afterIdx });
  };

  return (
    <div className="relative w-full h-full min-h-[620px] bg-[#02040a] rounded-2xl overflow-hidden border border-slate-800 shadow-2xl flex flex-col">
      {/* Space Atmospheric Halo Backdrop */}
      <div className="absolute inset-0 pointer-events-none z-10 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-cyan-950/20 via-transparent to-transparent" />

      {/* Top Orbital Intelligence HUD Bar */}
      <div className="absolute top-4 left-4 right-4 z-20 flex flex-wrap items-center justify-between gap-3 pointer-events-auto">
        {/* Left: Mission & Orbit Altitude Badge */}
        <div className="flex items-center gap-2.5 bg-[#091120]/90 border border-cyan-800/50 backdrop-blur-md px-3.5 py-2 rounded-xl shadow-lg">
          <Globe className="w-4 h-4 text-cyan-400 animate-pulse" />
          <div className="flex flex-col">
            <span className="text-[10px] text-cyan-400 font-mono tracking-widest uppercase">
              SATQUERY-X ORBITAL OBSERVATORY
            </span>
            <span className="text-xs font-bold text-slate-100 font-mono">{cameraAltitude}</span>
          </div>
        </div>

        {/* Center: Natural Language Earth Search Bar */}
        <form onSubmit={handleSearch} className="flex-1 max-w-md">
          <div className="relative flex items-center">
            <Search className="w-4 h-4 absolute left-3 text-cyan-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search Earth (e.g., 'Chennai', 'Pollachi agricultural areas')..."
              className="w-full bg-[#091120]/90 border border-slate-700/80 rounded-xl pl-9 pr-24 py-2 text-xs text-slate-100 placeholder-slate-400 focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400 backdrop-blur-md font-mono"
            />
            <button
              type="submit"
              className="absolute right-1.5 px-3 py-1 bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-bold rounded-lg text-xs transition-colors"
            >
              Orbit Fly-To
            </button>
          </div>
        </form>

        {/* Right: Preset Orbital Observation Targets */}
        <div className="flex items-center gap-1.5 bg-[#091120]/90 border border-slate-800 backdrop-blur-md p-1 rounded-xl">
          {ORBITAL_TARGETS.slice(0, 3).map((target) => (
            <button
              key={target.name}
              onClick={() => executeOrbitalDescent(target)}
              className={`px-2.5 py-1 text-[11px] rounded-lg font-medium transition-all ${
                activeTarget.name === target.name
                  ? 'bg-cyan-950 text-cyan-300 border border-cyan-700'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              {target.name.split(' ')[0]}
            </button>
          ))}
        </div>
      </div>

      {/* Main WebGL Globe Container */}
      <div ref={mapContainerRef} className="w-full flex-1 relative z-0" />

      {/* Floating Active Observation Info Badge (Top Right) */}
      <div className="absolute top-20 right-4 z-20 pointer-events-auto max-w-xs bg-[#091120]/90 border border-slate-800 rounded-xl p-3 backdrop-blur-md shadow-xl flex flex-col gap-2 text-xs">
        <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
          <div className="flex items-center gap-1.5 text-cyan-400 font-semibold font-mono text-[11px]">
            <Satellite className="w-3.5 h-3.5" />
            <span>REAL SATELLITE OBSERVATION</span>
          </div>
          <span className="text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800 px-1.5 py-0.5 rounded font-mono">
            COPERNICUS STAC v1
          </span>
        </div>

        <div className="space-y-1 text-slate-300">
          <div className="font-semibold text-slate-100">{activeTarget.name}</div>
          <div className="text-[11px] text-slate-400">{activeTarget.description}</div>
        </div>

        {timeline?.latest_observation && (
          <div className="bg-slate-900/80 rounded-lg p-2 border border-slate-800/80 space-y-1 font-mono text-[10px]">
            <div className="flex justify-between">
              <span className="text-slate-500">LATEST PASS:</span>
              <span className="text-cyan-300 font-bold">{timeline.latest_observation.observation_date}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">MISSION / SENSOR:</span>
              <span className="text-indigo-300">{timeline.latest_observation.platform} MSI</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">CLOUD COVER:</span>
              <span className="text-amber-400">
                {timeline.latest_observation.cloud_cover !== null
                  ? `${timeline.latest_observation.cloud_cover.toFixed(1)}%`
                  : '0.0%'}
              </span>
            </div>
          </div>
        )}

        {/* AI Quick Query Button */}
        {onAskAI && (
          <button
            onClick={() =>
              onAskAI(`What changed in ${activeTarget.name} between 2018 and 2026? Quantify urban and vegetation shifts.`)
            }
            className="w-full mt-1 flex items-center justify-center gap-1.5 py-1.5 bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white font-semibold text-[11px] rounded-lg shadow-md transition-all"
          >
            <Sparkles className="w-3.5 h-3.5 text-cyan-200" />
            <span>Ask AI About This Area</span>
          </button>
        )}
      </div>

      {/* Floating Change Detection Result Card (when event detected) */}
      {selectedChangeEvent && (
        <div className="absolute top-20 left-4 z-20 pointer-events-auto max-w-sm bg-[#091120]/95 border border-rose-900/60 rounded-xl p-3.5 backdrop-blur-md shadow-2xl flex flex-col gap-2">
          <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
            <span className="text-[11px] font-bold text-rose-400 flex items-center gap-1 font-mono">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>DETECTED GROUND CHANGE</span>
            </span>
            <span className="bg-rose-950 text-rose-300 border border-rose-800 px-1.5 py-0.5 rounded text-[10px] font-mono">
              {(selectedChangeEvent.confidence * 100).toFixed(0)}% CONFIDENCE
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <div className="bg-slate-900/80 p-2 rounded border border-slate-800">
              <span className="text-slate-500 text-[10px]">CHANGE CLASS</span>
              <div className="font-bold text-slate-100">{selectedChangeEvent.change_type}</div>
            </div>
            <div className="bg-slate-900/80 p-2 rounded border border-slate-800">
              <span className="text-slate-500 text-[10px]">SURFACE AREA</span>
              <div className="font-bold text-rose-300">{selectedChangeEvent.area_hectares} ha</div>
            </div>
          </div>

          <div className="text-[10px] text-slate-400 font-mono">
            Algorithm: <span className="text-slate-200">{selectedChangeEvent.algorithm}</span>
          </div>

          <button
            onClick={() => setSelectedChangeEvent(null)}
            className="text-[10px] text-slate-500 hover:text-slate-300 text-center mt-1"
          >
            Dismiss overlay
          </button>
        </div>
      )}

      {/* Bottom Docked Temporal Observation Timeline */}
      <div className="absolute bottom-4 left-4 right-4 z-20 pointer-events-auto">
        <TimelineSlider
          timeline={timeline}
          selectedObsIndex={selectedObsIndex}
          onSelectObservation={(idx) => {
            setSelectedObsIndex(idx);
          }}
          onCompare={handleCompare}
          onRunChangeDetection={handleRunChangeDetection}
          isAnalyzing={isAnalyzing}
        />
      </div>
    </div>
  );
};
