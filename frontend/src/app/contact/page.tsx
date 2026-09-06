"use client";

import { useState } from "react";
import { Mail, Phone, MapPin } from "lucide-react";
import PublicNavbar from "../../components/PublicNavbar";

export default function ContactPage() {
  const [sent, setSent] = useState(false);

  return (
    <>
      <PublicNavbar />
      <div className="public-page contact">
        <div>
          <span className="eyebrow">CONTACT / SUPPORT</span>
          <h1>Get in Touch</h1>
          <p>
            Have questions about satellite data integrations, API access, or planetary analytics?
            Reach out to our geospatial engineering team.
          </p>

          <div className="contact-info">
            <span>
              <Mail /> support@satquery.ai
            </span>
            <span>
              <Phone /> +91 98765 43210
            </span>
            <span>
              <MapPin /> Coimbatore, Tamil Nadu, India
            </span>
          </div>
        </div>

        <form
          className="panel form"
          onSubmit={(e) => {
            e.preventDefault();
            setSent(true);
          }}
        >
          <label>
            Name
            <input placeholder="Enter your name" required />
          </label>
          <label>
            Email
            <input type="email" placeholder="Enter your email" required />
          </label>
          <label>
            Message
            <textarea
              placeholder="How can our geospatial intelligence team help you?"
              rows={4}
              required
            />
          </label>

          {sent && <div className="info">Thank you! Your message has been dispatched to our engineering team.</div>}

          <button className="btn primary">Send Message</button>
        </form>
      </div>
    </>
  );
}
