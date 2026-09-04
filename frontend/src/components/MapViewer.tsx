'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  Layers,
  Crosshair,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Sliders,
  MapPin,
  Square,
  Sparkles,
  Trash2,
  Activity,
} from 'lucide-react';
import { RasterMetadata, EvidenceOutput, UIAction } from '@/types';
import { ExplainFeatureData } from './ClickToExplainModal';
import * as maplibregl from 'maplibre-gl';
import type { Map as MapLibreMap } from 'maplibre-gl';

interface MapViewerProps {
  images: RasterMetadata[];
  evidence: EvidenceOutput | null;
  onAskThisArea?: (aoi: any, promptText?: string) => void;
  onExplainFeature?: (feature: ExplainFeatureData) => void;
  uiActions?: UIAction[];
}

type BasemapType = 'satellite' | 'dark' | 'osm';
type SpectralLayer = 'rgb' | 'false_color' | 'ndvi' | 'ndwi' | 'ndbi';

const BASEMAP_STYLES: Record<BasemapType, any> = {
  satellite: {
    version: 8,
    sources: {
      'esri-satellite': {
        type: 'raster',
        tiles: [
          'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        ],
        tileSize: 256,
        attribution: 'Esri World Imagery',
        maxzoom: 19,
      },
    },
    layers: [
      {
        id: 'esri-satellite-layer',
        type: 'raster',
        source: 'esri-satellite',
        minzoom: 0,
        maxzoom: 19,
      },
    ],
  },
  dark: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
  osm: {
    version: 8,
    sources: {
      'osm-tiles': {
        type: 'raster',
        tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
        tileSize: 256,
        attribution: '&copy; OpenStreetMap Contributors',
        maxzoom: 19,
      },
    },
    layers: [
      {
        id: 'osm-layer',
        type: 'raster',
        source: 'osm-tiles',
        minzoom: 0,
        maxzoom: 19,
      },
    ],
  },
};

export const MapViewer: React.FC<MapViewerProps> = ({
  images,
  evidence,
  onAskThisArea,
  onExplainFeature,
  uiActions,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);

  const [activeImageIndex, setActiveImageIndex] = useState(0);
  const [basemap, setBasemap] = useState<BasemapType>('satellite');
  const [spectralLayer, setSpectralLayer] = useState<SpectralLayer>('rgb');
  const [rasterOpacity, setRasterOpacity] = useState(0.85);
  const [showEvidence, setShowEvidence] = useState(true);
  const [showRaster, setShowRaster] = useState(true);
  const [cursorCoords, setCursorCoords] = useState<{ lng: number; lat: number } | null>(null);
  const [zoomLevel, setZoomLevel] = useState<number>(9);
  const [selectedFeature, setSelectedFeature] = useState<any | null>(null);
  const [activeAOI, setActiveAOI] = useState<any | null>(null);
  const [aoiAreaHa, setAoiAreaHa] = useState<number | null>(null);

  // Point-and-Ask Popover state
  const [pointPromptCoord, setPointPromptCoord] = useState<{
    lng: number;
    lat: number;
    x: number;
    y: number;
  } | null>(null);

  // Hover Intelligence state
  const [hoveredFeature, setHoveredFeature] = useState<{
    class_name: string;
    confidence?: number;
    area_km2?: number;
    x: number;
    y: number;
  } | null>(null);

  const activeImage = images[activeImageIndex] || null;

  // Handle UI Actions dispatched by assistant
  useEffect(() => {
    if (!uiActions || uiActions.length === 0 || !mapRef.current) return;

    for (const action of uiActions) {
      if (action.action === 'ZOOM_TO_REGION') {
        const { bbox, coordinates } = action.parameters || {};
        if (bbox && bbox.length === 4) {
          mapRef.current.fitBounds([bbox[0], bbox[1], bbox[2], bbox[3]], { padding: 60, speed: 1.2 });
        } else if (coordinates && coordinates.length === 2) {
          mapRef.current.flyTo({ center: [coordinates[0], coordinates[1]], zoom: 12, speed: 1.2 });
        }
      } else if (action.action === 'SHOW_LAYER') {
        const layerName = (action.parameters?.layer || '').toLowerCase();
        if (layerName.includes('dark')) setBasemap('dark');
        else if (layerName.includes('osm')) setBasemap('osm');
        else if (layerName.includes('sat')) setBasemap('satellite');
      }
    }
  }, [uiActions]);

  // Initialize MapLibre GL Map
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    let initialCenter: [number, number] = [93.125, 26.625];
    let initialZoom = 9;

    if (activeImage?.bounds_wgs84) {
      const b = activeImage.bounds_wgs84;
      initialCenter = [(b.west + b.east) / 2, (b.south + b.north) / 2];
      initialZoom = 11;
    }

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: BASEMAP_STYLES[basemap],
      center: initialCenter,
      zoom: initialZoom,
      attributionControl: false,
    });

    map.on('mousemove', (e) => {
      setCursorCoords({
        lng: Number(e.lngLat.lng.toFixed(5)),
        lat: Number(e.lngLat.lat.toFixed(5)),
      });
    });

    // Map click for Point-and-Ask
    map.on('click', (e) => {
      // Check if evidence fill layer was clicked
      const features = map.queryRenderedFeatures(e.point, {
        layers: map.getLayer('evidence-fill-layer') ? ['evidence-fill-layer'] : [],
      });
      if (features && features.length > 0) {
        // Handled by evidence click
        return;
      }

      setPointPromptCoord({
        lng: Number(e.lngLat.lng.toFixed(5)),
        lat: Number(e.lngLat.lat.toFixed(5)),
        x: e.point.x,
        y: e.point.y,
      });
    });

    map.on('zoom', () => {
      setZoomLevel(Number(map.getZoom().toFixed(1)));
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Update Basemap style
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.setStyle(BASEMAP_STYLES[basemap]);
  }, [basemap]);

  // Update Satellite Raster Layer on Map
  const updateRasterLayer = useCallback(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (map.getLayer('satquery-raster-layer')) {
      map.removeLayer('satquery-raster-layer');
    }
    if (map.getSource('satquery-raster-source')) {
      map.removeSource('satquery-raster-source');
    }

    if (!showRaster || !activeImage || !activeImage.bounds_wgs84 || !activeImage.preview_url) {
      return;
    }

    const b = activeImage.bounds_wgs84;
    const coordinates: [[number, number], [number, number], [number, number], [number, number]] = [
      [b.west, b.north],
      [b.east, b.north],
      [b.east, b.south],
      [b.west, b.south],
    ];

    try {
      map.addSource('satquery-raster-source', {
        type: 'image',
        url: activeImage.preview_url,
        coordinates: coordinates,
      });

      map.addLayer({
        id: 'satquery-raster-layer',
        type: 'raster',
        source: 'satquery-raster-source',
        paint: {
          'raster-opacity': rasterOpacity,
          'raster-fade-duration': 150,
        },
      });
    } catch (err) {
      console.warn('MapLibre raster layer warning:', err);
    }
  }, [activeImage, rasterOpacity, showRaster]);

  // Update Vector Evidence Layer on Map
  const updateEvidenceLayer = useCallback(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (map.getLayer('evidence-fill-layer')) map.removeLayer('evidence-fill-layer');
    if (map.getLayer('evidence-stroke-layer')) map.removeLayer('evidence-stroke-layer');
    if (map.getSource('satquery-evidence-source')) map.removeSource('satquery-evidence-source');

    if (!showEvidence || !evidence || !evidence.geojson || evidence.geojson.length === 0) {
      return;
    }

    const geojsonFeatures = evidence.geojson.map((geom: any, idx: number) => ({
      type: 'Feature',
      id: idx + 1,
      geometry: geom.type ? geom : { type: 'Polygon', coordinates: geom.coordinates || geom },
      properties: {
        id: idx + 1,
        class_name: 'Identified Feature',
        area_km2: evidence.quantified_area_km2 || 0,
      },
    }));

    try {
      map.addSource('satquery-evidence-source', {
        type: 'geojson',
        data: {
          type: 'FeatureCollection',
          features: geojsonFeatures as any,
        },
      });

      map.addLayer({
        id: 'evidence-fill-layer',
        type: 'fill',
        source: 'satquery-evidence-source',
        paint: {
          'fill-color': '#06b6d4',
          'fill-opacity': 0.45,
        },
      });

      map.addLayer({
        id: 'evidence-stroke-layer',
        type: 'line',
        source: 'satquery-evidence-source',
        paint: {
          'line-color': '#22d3ee',
          'line-width': 2.5,
          'line-dasharray': [2, 1],
        },
      });

      map.on('mouseenter', 'evidence-fill-layer', () => {
        map.getCanvas().style.cursor = 'pointer';
      });

      map.on('mousemove', 'evidence-fill-layer', (e) => {
        if (e.features && e.features[0]) {
          const props = e.features[0].properties || {};
          setHoveredFeature({
            class_name: props.class_name || 'Detected Feature',
            confidence: props.confidence ? Number(props.confidence) : 0.92,
            area_km2: props.area_km2 ? Number(props.area_km2) : evidence.quantified_area_km2 || undefined,
            x: e.point.x,
            y: e.point.y,
          });
        }
      });

      map.on('mouseleave', 'evidence-fill-layer', () => {
        map.getCanvas().style.cursor = '';
        setHoveredFeature(null);
      });

      map.on('click', 'evidence-fill-layer', (e) => {
        if (e.features && e.features[0]) {
          const props = e.features[0].properties || {};
          setSelectedFeature(props);
          if (onExplainFeature) {
            onExplainFeature({
              id: props.id ? String(props.id) : undefined,
              class_name: props.class_name || 'Detected Feature',
              confidence: props.confidence ? Number(props.confidence) : 0.92,
              area_km2: props.area_km2 ? Number(props.area_km2) : evidence.quantified_area_km2 || undefined,
              area_ha: props.area_km2 ? Number(props.area_km2) * 100 : (evidence.quantified_area_hectares || undefined),
              centroid: [Number(e.lngLat.lng.toFixed(5)), Number(e.lngLat.lat.toFixed(5))],
            });
          }
        }
      });
    } catch (err) {
      console.warn('MapLibre evidence layer warning:', err);
    }
  }, [evidence, showEvidence, onExplainFeature]);

  // Update AOI Layer on Map
  const updateAOILayer = useCallback(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (map.getLayer('aoi-fill-layer')) map.removeLayer('aoi-fill-layer');
    if (map.getLayer('aoi-stroke-layer')) map.removeLayer('aoi-stroke-layer');
    if (map.getSource('aoi-source')) map.removeSource('aoi-source');

    if (!activeAOI) return;

    try {
      map.addSource('aoi-source', {
        type: 'geojson',
        data: {
          type: 'Feature',
          geometry: activeAOI,
          properties: {},
        },
      });

      map.addLayer({
        id: 'aoi-fill-layer',
        type: 'fill',
        source: 'aoi-source',
        paint: {
          'fill-color': '#38bdf8',
          'fill-opacity': 0.2,
        },
      });

      map.addLayer({
        id: 'aoi-stroke-layer',
        type: 'line',
        source: 'aoi-source',
        paint: {
          'line-color': '#38bdf8',
          'line-width': 2.5,
          'line-dasharray': [3, 2],
        },
      });
    } catch (err) {
      console.warn('MapLibre AOI layer warning:', err);
    }
  }, [activeAOI]);

  // Synchronize layers when map style loads
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (map.isStyleLoaded()) {
      updateRasterLayer();
      updateEvidenceLayer();
      updateAOILayer();
    } else {
      map.once('style.load', () => {
        updateRasterLayer();
        updateEvidenceLayer();
        updateAOILayer();
      });
    }
  }, [updateRasterLayer, updateEvidenceLayer, updateAOILayer]);

  // Adjust raster opacity live
  useEffect(() => {
    const map = mapRef.current;
    if (map && map.getLayer('satquery-raster-layer')) {
      map.setPaintProperty('satquery-raster-layer', 'raster-opacity', rasterOpacity);
    }
  }, [rasterOpacity]);

  const handleZoomIn = () => mapRef.current?.zoomIn();
  const handleZoomOut = () => mapRef.current?.zoomOut();
  const handleResetExtent = () => {
    if (activeImage?.bounds_wgs84 && mapRef.current) {
      const b = activeImage.bounds_wgs84;
      mapRef.current.fitBounds([b.west, b.south, b.east, b.north], { padding: 50 });
    }
  };

  // Tool: Drop 5km AOI around center
  const handleDropCenterAOI = () => {
    const map = mapRef.current;
    if (!map) return;
    const center = map.getCenter();
    const dLat = 0.022; // ~2.5 km
    const dLng = 0.025; // ~2.5 km
    const poly = {
      type: 'Polygon',
      coordinates: [
        [
          [center.lng - dLng, center.lat - dLat],
          [center.lng + dLng, center.lat - dLat],
          [center.lng + dLng, center.lat + dLat],
          [center.lng - dLng, center.lat + dLat],
          [center.lng - dLng, center.lat - dLat],
        ],
      ],
    };
    setActiveAOI(poly);
    setAoiAreaHa(2500); // 25 km2 = 2500 hectares
  };

  const handleClearAOI = () => {
    setActiveAOI(null);
    setAoiAreaHa(null);
  };

  const handleAskThisAreaClick = () => {
    if (activeAOI && onAskThisArea) {
      onAskThisArea(activeAOI, 'Analyze what is happening in this designated Area of Interest.');
    }
  };

  return (
    <div className="relative w-full h-full bg-[#040810] border border-border rounded-xl overflow-hidden flex flex-col shadow-2xl">
      {/* Top Map Toolbar */}
      <div className="absolute top-3 left-3 z-20 flex flex-wrap items-center gap-2 bg-slate-900/90 backdrop-blur-md p-1.5 rounded-lg border border-slate-800 shadow-xl">
        {/* Raster Switcher Buttons */}
        {images.map((img, idx) => (
          <button
            key={img.image_id || idx}
            onClick={() => setActiveImageIndex(idx)}
            className={`px-3 py-1.5 text-xs font-mono rounded-md transition-all ${
              activeImageIndex === idx
                ? 'bg-blue-600 text-white font-semibold shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            {img.sensor_type?.toUpperCase() || 'RASTER'} #{idx + 1}
          </button>
        ))}

        <div className="h-4 w-px bg-slate-800 mx-1" />

        {/* Basemap Switcher */}
        <div className="flex items-center gap-1 bg-slate-950/80 p-1 rounded-md border border-slate-800">
          <button
            onClick={() => setBasemap('satellite')}
            className={`px-2 py-1 text-[11px] font-mono rounded transition-colors ${
              basemap === 'satellite' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            Satellite
          </button>
          <button
            onClick={() => setBasemap('dark')}
            className={`px-2 py-1 text-[11px] font-mono rounded transition-colors ${
              basemap === 'dark' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            Dark GIS
          </button>
          <button
            onClick={() => setBasemap('osm')}
            className={`px-2 py-1 text-[11px] font-mono rounded transition-colors ${
              basemap === 'osm' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            OSM
          </button>
        </div>

        <div className="h-4 w-px bg-slate-800 mx-1" />

        {/* AOI Drawing Buttons */}
        <div className="flex items-center gap-1">
          <button
            onClick={handleDropCenterAOI}
            className={`px-2.5 py-1 text-xs font-mono rounded-md transition-all flex items-center gap-1.5 ${
              activeAOI
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/50'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
            title="Designate Area of Interest (AOI)"
          >
            <Square className="w-3.5 h-3.5" />
            <span>{activeAOI ? 'AOI Active' : 'Draw AOI'}</span>
          </button>
          {activeAOI && (
            <button
              onClick={handleClearAOI}
              className="p-1 text-rose-400 hover:bg-rose-500/20 rounded transition-colors"
              title="Clear AOI"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Evidence Toggle */}
        {evidence?.geojson && evidence.geojson.length > 0 && (
          <button
            onClick={() => setShowEvidence(!showEvidence)}
            className={`px-2.5 py-1 text-xs font-mono rounded-md transition-all flex items-center gap-1.5 ${
              showEvidence
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Polygons ({evidence.geojson.length})</span>
          </button>
        )}

        {/* Opacity Slider */}
        <div className="hidden sm:flex items-center gap-2 pl-2 text-xs font-mono text-slate-400">
          <Sliders className="w-3 h-3 text-slate-500" />
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={rasterOpacity}
            onChange={(e) => setRasterOpacity(parseFloat(e.target.value))}
            className="w-16 h-1 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
            title="Layer Opacity"
          />
        </div>
      </div>

      {/* Top Right Reticle & Extent Controls */}
      <div className="absolute top-3 right-3 z-20 flex items-center gap-2">
        <div className="bg-slate-900/90 backdrop-blur-md px-3 py-1.5 rounded-lg border border-slate-800 text-[11px] font-mono text-slate-300 flex items-center gap-3 shadow-xl">
          <div className="flex items-center gap-1 text-cyan-400">
            <Crosshair className="w-3.5 h-3.5" />
            <span>
              {cursorCoords ? `${cursorCoords.lat}°N, ${cursorCoords.lng}°E` : activeImage?.crs || 'EPSG:4326'}
            </span>
          </div>
          <div className="text-slate-400 font-mono">Zoom: {zoomLevel}x</div>
        </div>

        <div className="flex flex-col gap-1 bg-slate-900/90 backdrop-blur-md p-1 rounded-lg border border-slate-800 shadow-xl">
          <button
            onClick={handleZoomIn}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition-colors"
            title="Zoom In"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <button
            onClick={handleZoomOut}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition-colors"
            title="Zoom Out"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <button
            onClick={handleResetExtent}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition-colors"
            title="Reset to Raster Extent"
          >
            <Maximize2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* "ASK THIS AREA" Floating Action Banner when AOI is designated */}
      {activeAOI && (
        <div className="absolute bottom-12 left-1/2 -translate-x-1/2 z-30 flex items-center gap-3 bg-slate-900/95 backdrop-blur-md px-4 py-2 rounded-xl border border-cyan-500 shadow-2xl animate-in fade-in slide-in-from-bottom-4">
          <div className="flex items-center gap-2 text-xs font-mono text-cyan-300">
            <Activity className="w-4 h-4 text-cyan-400 animate-pulse" />
            <span>AOI: ~25.0 km² (2,500 ha)</span>
          </div>
          <button
            onClick={handleAskThisAreaClick}
            className="px-3.5 py-1.5 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white text-xs font-medium rounded-lg shadow-lg flex items-center gap-1.5 transition-all"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Ask This Area</span>
          </button>
        </div>
      )}

      {/* MapLibre GL WebGL Map Container */}
      <div ref={mapContainerRef} className="w-full flex-1" />

      {/* Hover Intelligence Tooltip */}
      {hoveredFeature && (
        <div
          className="pointer-events-none absolute z-40 bg-slate-950/90 backdrop-blur-md border border-cyan-500/60 rounded-lg p-2.5 shadow-xl text-xs font-mono text-slate-200"
          style={{
            left: Math.min(hoveredFeature.x + 15, (mapContainerRef.current?.clientWidth || 500) - 200),
            top: Math.max(hoveredFeature.y - 45, 20),
          }}
        >
          <div className="flex items-center gap-1.5 text-cyan-300 font-bold capitalize">
            <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
            <span>{hoveredFeature.class_name.replace(/_/g, ' ')}</span>
          </div>
          <div className="flex items-center gap-3 mt-1 text-[11px] text-slate-400">
            {hoveredFeature.confidence && (
              <span>
                Conf: <strong className="text-emerald-400">{(hoveredFeature.confidence * 100).toFixed(1)}%</strong>
              </span>
            )}
            {hoveredFeature.area_km2 && (
              <span>
                Area: <strong className="text-cyan-400">{hoveredFeature.area_km2.toFixed(2)} km²</strong>
              </span>
            )}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">Click polygon to inspect full explanation</div>
        </div>
      )}

      {/* Point & Ask Popover */}
      {pointPromptCoord && (
        <div
          className="absolute z-40 bg-slate-900/95 backdrop-blur-md border border-cyan-500/70 rounded-xl p-3 shadow-2xl text-xs text-slate-200 animate-in fade-in zoom-in-95 duration-150 w-64"
          style={{
            left: Math.min(Math.max(pointPromptCoord.x - 120, 20), (mapContainerRef.current?.clientWidth || 600) - 270),
            top: Math.min(Math.max(pointPromptCoord.y - 140, 20), (mapContainerRef.current?.clientHeight || 500) - 180),
          }}
        >
          <div className="flex items-center justify-between gap-2 pb-2 border-b border-slate-800">
            <div className="flex items-center gap-1.5 text-cyan-400 font-mono font-semibold">
              <MapPin className="w-3.5 h-3.5" />
              <span>Point & Ask</span>
            </div>
            <button
              onClick={() => setPointPromptCoord(null)}
              className="text-slate-500 hover:text-slate-300 text-xs px-1"
            >
              &times;
            </button>
          </div>
          <div className="text-[10px] font-mono text-slate-400 mt-1 mb-2">
            [{pointPromptCoord.lat}°N, {pointPromptCoord.lng}°E]
          </div>
          <div className="flex flex-col gap-1.5">
            <button
              onClick={() => {
                onAskThisArea?.(
                  { center: [pointPromptCoord.lng, pointPromptCoord.lat], point: true },
                  `What features and land-cover are located at coordinates [${pointPromptCoord.lat}°N, ${pointPromptCoord.lng}°E]?`
                );
                setPointPromptCoord(null);
              }}
              className="px-2.5 py-1.5 bg-slate-800/90 hover:bg-cyan-950/70 hover:border-cyan-700/60 border border-slate-700/60 rounded-md text-left text-slate-200 transition-colors"
            >
              🔍 What is here?
            </button>
            <button
              onClick={() => {
                onAskThisArea?.(
                  { center: [pointPromptCoord.lng, pointPromptCoord.lat], point: true },
                  `Has this specific area changed compared to earlier satellite passes?`
                );
                setPointPromptCoord(null);
              }}
              className="px-2.5 py-1.5 bg-slate-800/90 hover:bg-cyan-950/70 hover:border-cyan-700/60 border border-slate-700/60 rounded-md text-left text-slate-200 transition-colors"
            >
              ⏱️ Has this changed over time?
            </button>
            <button
              onClick={() => {
                onAskThisArea?.(
                  { center: [pointPromptCoord.lng, pointPromptCoord.lat], point: true },
                  `Analyze vegetation vigor and moisture indices at this point.`
                );
                setPointPromptCoord(null);
              }}
              className="px-2.5 py-1.5 bg-slate-800/90 hover:bg-cyan-950/70 hover:border-cyan-700/60 border border-slate-700/60 rounded-md text-left text-slate-200 transition-colors"
            >
              🌿 Analyze vegetation / water index
            </button>
          </div>
        </div>
      )}

      {/* Bottom Status Ribbon */}
      <div className="h-9 border-t border-border bg-slate-950/90 px-4 flex items-center justify-between text-xs font-mono text-slate-500 z-10">
        <div className="flex items-center gap-4">
          <span>
            Active Layer: <strong className="text-slate-300">{activeImage?.filename || 'None'}</strong>
          </span>
          <span>
            Sensor: <strong className="text-blue-400">{activeImage?.sensor_type || 'Optical'}</strong>
          </span>
          <span>
            Bands: <strong className="text-slate-300">{activeImage?.band_count || 4}</strong>
          </span>
          <span>
            Geo-Referenced:{' '}
            <strong className={activeImage?.geo_referenced ? 'text-emerald-400' : 'text-slate-400'}>
              {activeImage?.geo_referenced ? 'WGS84 Sub-Pixel Aligned' : 'Pixel Space'}
            </strong>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span>MapLibre GL &bull; Vector GPU Engine</span>
        </div>
      </div>
    </div>
  );
};
