"use client";

import { Globe2, Users, Sprout } from "lucide-react";
import PublicNavbar from "../../components/PublicNavbar";

export default function AboutPage() {
  return (
    <>
      <PublicNavbar />
      <div className="public-page">
        <div className="about-hero">
          <div>
            <span className="eyebrow">ABOUT SATQUERY AI</span>
            <h1>
              Cleaner data.
              <br />
              <span>Smarter decisions.</span>
            </h1>
            <p>
              SatQuery AI is an autonomous, multi-agent geospatial intelligence engine designed to make
              complex satellite image reasoning accessible through natural language. By uniting
              Copernicus Earth observation data, vision-language foundation models, and deterministic
              geodesic verification, SatQuery delivers actionable planetary intelligence with zero
              hallucination.
            </p>
          </div>
          <img
            src="https://images.unsplash.com/photo-1446776811953-b23d57bd21aa?auto=format&fit=crop&w=1000&q=80"
            alt="Earth from Space"
          />
        </div>

        <section className="mission">
          <h2>Our Mission</h2>
          <p>
            Leverage AI and remote sensing data for a cleaner, safer, and more sustainable planet.
          </p>

          <div className="mission-grid">
            <div>
              <Users />
              <b>People</b>
              <span>Make Earth observation understandable to scientists, planners, and citizens.</span>
            </div>
            <div>
              <Globe2 />
              <b>Planet</b>
              <span>Transform high-dimensional multispectral pixels into verified, measurable insights.</span>
            </div>
            <div>
              <Sprout />
              <b>Progress</b>
              <span>Support climate resilience, agricultural yield, and disaster response with evidence.</span>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}
