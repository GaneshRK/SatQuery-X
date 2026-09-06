"use client";

import { useState } from "react";
import AppShell from "../../components/AppShell";
import SectionTitle from "../../components/SectionTitle";
import { useAuth } from "../../context/AuthContext";

export default function SettingsPage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState("Account");
  const [fullName, setFullName] = useState(user?.full_name || "Ganesh K");
  const [saved, setSaved] = useState(false);

  return (
    <AppShell>
      <div className="page settings-page">
        <SectionTitle
          title="Profile & Settings"
          subtitle="Manage your analyst profile, sensor preferences, and API configuration."
        />

        <div className="settings-grid">
          <div className="settings-nav">
            {["Account", "Preferences", "Sensor Feeds", "API Keys", "Data & Security"].map((tab) => (
              <button
                key={tab}
                className={activeTab === tab ? "active" : ""}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>

          <div className="panel settings-form">
            <div className="avatar-large">
              {(user?.full_name || "G").slice(0, 1).toUpperCase()}
            </div>

            <label>
              Full Name
              <input
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </label>

            <label>
              Email Address
              <input value={user?.email || "analyst@satquery.ai"} readOnly />
            </label>

            <button className="btn ghost" type="button">
              Change Password
            </button>

            <hr />

            <h3>Appearance & Themes</h3>
            <div className="theme-row">
              <button className="active">◐ Planetary Dark</button>
              <button>☀ High Contrast</button>
              <button>System</button>
            </div>

            <label>
              Default Satellite Constellation
              <select defaultValue="Sentinel-2 L2A (Multispectral)">
                <option>Sentinel-2 L2A (Multispectral)</option>
                <option>Sentinel-1 GRD (C-Band SAR)</option>
                <option>Landsat 8/9 OLI</option>
                <option>Cartosat-2S High-Res</option>
              </select>
            </label>

            <label>
              Language
              <select defaultValue="English">
                <option>English</option>
                <option>Tamil</option>
                <option>Hindi</option>
              </select>
            </label>

            <button
              className="btn primary"
              type="button"
              onClick={() => {
                setSaved(true);
                setTimeout(() => setSaved(false), 2500);
              }}
            >
              {saved ? "Settings Saved ✓" : "Save Changes"}
            </button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
