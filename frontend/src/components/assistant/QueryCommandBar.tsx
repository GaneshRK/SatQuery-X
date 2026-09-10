"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Send,
  Upload,
  Mic,
  MicOff,
  MapPin,
  Calendar,
  X,
  Sparkles,
  SlidersHorizontal,
} from "lucide-react";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";

export interface QueryContext {
  location?: string | null;
  sensor?: string;
  startDate?: string;
  endDate?: string;
  targetRegionId?: string | null;
  hasUploadedImage?: boolean;
}

export interface QueryCommandBarProps {
  onSend: (text: string, context?: QueryContext) => void;
  isLoading?: boolean;
  initialQuery?: string;
  activeContext?: QueryContext;
  onContextChange?: (newContext: QueryContext) => void;
  onOpenUpload?: () => void;
  onOpenLocationPicker?: () => void;
  placeholder?: string;
}

export const QueryCommandBar: React.FC<QueryCommandBarProps> = ({
  onSend,
  isLoading = false,
  initialQuery = "",
  activeContext = {
    location: "",
    sensor: "SENTINEL-2",
  },
  onContextChange,
  onOpenUpload,
  onOpenLocationPicker,
  placeholder,
}) => {
  const [text, setText] = useState(initialQuery);
  const [isListening, setIsListening] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (initialQuery) setText(initialQuery);
  }, [initialQuery]);

  // Adjust textarea height dynamically
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 140)}px`;
    }
  }, [text]);

  // Speech to text integration
  const toggleVoiceInput = () => {
    if (typeof window === "undefined") return;
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert("Voice input is not supported in this browser. Please type your query.");
      return;
    }

    if (isListening) {
      setIsListening(false);
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.lang = "en-US";
      recognition.continuous = false;
      recognition.interimResults = false;

      recognition.onstart = () => setIsListening(true);
      recognition.onend = () => setIsListening(false);
      recognition.onerror = () => setIsListening(false);

      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        setText((prev) => (prev ? `${prev} ${transcript}` : transcript));
      };

      recognition.start();
    } catch (err) {
      console.warn("Speech recognition error:", err);
      setIsListening(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed, activeContext);
    setText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const computedPlaceholder =
    placeholder ||
    (activeContext?.targetRegionId
      ? `Ask about selected region ${activeContext.targetRegionId}...`
      : activeContext?.hasUploadedImage
      ? "Ask about this uploaded satellite imagery..."
      : activeContext?.location
      ? `Ask anything about ${activeContext.location} (e.g. What changed since 2020?)...`
      : "Ask anything about Earth's satellite imagery...");

  return (
    <div className="w-full bg-slate-900/90 backdrop-blur-md border border-slate-800/90 rounded-2xl p-3.5 shadow-2xl shadow-black/40 transition-all focus-within:border-cyan-500/50 focus-within:ring-1 focus-within:ring-cyan-500/30">
      {/* Context Chips Bar */}
      {(activeContext?.location ||
        activeContext?.targetRegionId ||
        activeContext?.hasUploadedImage ||
        activeContext?.sensor) && (
        <div className="flex flex-wrap items-center gap-1.5 mb-2.5 pb-2 border-b border-slate-800/60">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mr-1 select-none">
            Active Context:
          </span>

          {activeContext.location && (
            <Badge variant="info" size="sm" className="gap-1.5 py-0.5">
              <MapPin className="w-2.5 h-2.5 text-cyan-400" />
              <span>{activeContext.location}</span>
              {onContextChange && (
                <button
                  type="button"
                  onClick={() => onContextChange({ ...activeContext, location: null })}
                  className="hover:text-cyan-100 ml-0.5"
                  title="Remove location filter"
                >
                  <X className="w-2.5 h-2.5" />
                </button>
              )}
            </Badge>
          )}

          {activeContext.targetRegionId && (
            <Badge variant="warning" size="sm" className="gap-1.5 py-0.5">
              <span>Focus: {activeContext.targetRegionId}</span>
              {onContextChange && (
                <button
                  type="button"
                  onClick={() => onContextChange({ ...activeContext, targetRegionId: null })}
                  className="hover:text-amber-100 ml-0.5"
                  title="Clear region focus"
                >
                  <X className="w-2.5 h-2.5" />
                </button>
              )}
            </Badge>
          )}

          {activeContext.sensor && (
            <Badge variant="satellite" size="sm" className="gap-1 py-0.5">
              <span>{activeContext.sensor}</span>
            </Badge>
          )}

          {activeContext.hasUploadedImage && (
            <Badge variant="success" size="sm" className="gap-1 py-0.5">
              <span>Image Attached</span>
            </Badge>
          )}

          <button
            type="button"
            onClick={() => setShowAdvanced((prev) => !prev)}
            className="ml-auto text-[11px] text-slate-400 hover:text-slate-200 flex items-center gap-1 transition-colors"
          >
            <SlidersHorizontal className="w-3 h-3" />
            <span>{showAdvanced ? "Hide settings" : "Advanced"}</span>
          </button>
        </div>
      )}

      {/* Advanced Drawer / Controls */}
      {showAdvanced && (
        <div className="mb-3 p-3 rounded-xl bg-slate-950/60 border border-slate-800 grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs">
          <div>
            <label className="text-[10px] text-slate-400 font-semibold uppercase block mb-1">
              Sensor Constellation
            </label>
            <select
              value={activeContext?.sensor || "SENTINEL-2"}
              onChange={(e) =>
                onContextChange?.({ ...activeContext, sensor: e.target.value })
              }
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
            >
              <option value="SENTINEL-2">Sentinel-2 (Optical 10m VNIR/SWIR)</option>
              <option value="SENTINEL-1">Sentinel-1 (SAR Radar C-band)</option>
              <option value="LANDSAT-8/9">Landsat 8/9 (OLI-2 / TIRS Thermal)</option>
            </select>
          </div>
          <div>
            <label className="text-[10px] text-slate-400 font-semibold uppercase block mb-1">
              Temporal Window Start
            </label>
            <input
              type="date"
              value={activeContext?.startDate || ""}
              onChange={(e) =>
                onContextChange?.({ ...activeContext, startDate: e.target.value })
              }
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
            />
          </div>
          <div>
            <label className="text-[10px] text-slate-400 font-semibold uppercase block mb-1">
              Temporal Window End
            </label>
            <input
              type="date"
              value={activeContext?.endDate || ""}
              onChange={(e) =>
                onContextChange?.({ ...activeContext, endDate: e.target.value })
              }
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
            />
          </div>
        </div>
      )}

      {/* Main Multiline Input */}
      <div className="relative flex items-start gap-2">
        <textarea
          ref={textareaRef}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={computedPlaceholder}
          disabled={isLoading}
          className="flex-1 bg-transparent text-sm text-slate-100 placeholder-slate-500 resize-none focus:outline-none min-h-[44px] max-h-[140px] py-2 px-1 leading-relaxed"
        />

        <div className="flex items-center gap-1.5 pt-1">
          {onOpenLocationPicker && (
            <button
              type="button"
              onClick={onOpenLocationPicker}
              className="p-2 rounded-lg text-slate-400 hover:text-cyan-300 hover:bg-slate-800/80 transition-colors"
              title="Set target location / coordinates"
            >
              <MapPin className="w-4 h-4" />
            </button>
          )}

          {onOpenUpload && (
            <button
              type="button"
              onClick={onOpenUpload}
              className="p-2 rounded-lg text-slate-400 hover:text-cyan-300 hover:bg-slate-800/80 transition-colors"
              title="Upload custom satellite raster"
            >
              <Upload className="w-4 h-4" />
            </button>
          )}

          <button
            type="button"
            onClick={toggleVoiceInput}
            className={`p-2 rounded-lg transition-colors ${
              isListening
                ? "bg-rose-950/60 text-rose-400 border border-rose-500/50 animate-pulse"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/80"
            }`}
            title={isListening ? "Listening... click to stop" : "Voice input (Speech to Text)"}
          >
            {isListening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
          </button>

          <Button
            variant="primary"
            size="md"
            isLoading={isLoading}
            disabled={!text.trim() || isLoading}
            onClick={handleSubmit}
            className="px-4 shrink-0 font-semibold"
            rightIcon={<Send className="w-3.5 h-3.5" />}
          >
            Analyze
          </Button>
        </div>
      </div>

      {/* Keyboard Helper Hint */}
      <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-800/40 text-[10px] text-slate-500 select-none">
        <span>
          Press <kbd className="px-1 py-0.5 bg-slate-800 rounded text-slate-400">Enter ↵</kbd> to analyze,{" "}
          <kbd className="px-1 py-0.5 bg-slate-800 rounded text-slate-400">Shift + Enter</kbd> for newline
        </span>
        <span className="text-slate-400">Powered by Copernicus Sentinel & ChangeFormer</span>
      </div>
    </div>
  );
};
