"use client";

import { useEffect, useState } from "react";
import { healthCheck } from "@/lib/api";

export default function HomePage() {
  const [health, setHealth] = useState<any>(null);

  useEffect(() => {
    healthCheck()
      .then(setHealth)
      .catch(() => setHealth({ status: "unreachable" }));
  }, []);

  return (
    <div>
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-kea-800 mb-4">
          KeaBuilder AI Platform
        </h1>
        <p className="text-lg text-gray-600 max-w-2xl mx-auto">
          AI-powered lead intelligence, multi-modal content generation,
          personalised brand imagery, and smart asset search — all in one platform.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-12">
        <FeatureCard
          href="/leads"
          title="Lead Intelligence"
          description="AI classifies leads as HOT/WARM/COLD and generates personalised responses automatically."
          badge="Q1"
        />
        <FeatureCard
          href="/generate"
          title="Content Generator"
          description="Generate images, voice, and video with a unified API — provider-agnostic routing."
          badge="Q2"
        />
        <FeatureCard
          href="/brand-kit"
          title="Brand Kit (LoRA)"
          description="Train a personalised AI model on your brand. Every generated image stays on-brand."
          badge="Q3"
        />
        <FeatureCard
          href="/assets"
          title="Similarity Search"
          description="Find visually or semantically similar assets. Face search, text match, CLIP embeddings."
          badge="Q4"
        />
        <FeatureCard
          href="#"
          title="Resilience Layer"
          description="Circuit breakers, fallbacks, and degraded modes keep the platform running even when providers fail."
          badge="Q5"
        />
        <FeatureCard
          href="#"
          title="Scale Infrastructure"
          description="Async job queues, priority lanes, GPU auto-scaling — handles 10K+ concurrent requests."
          badge="Q6"
        />
      </div>

      {health && (
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-3">System Status</h2>
          <div className="flex items-center space-x-2 mb-4">
            <div
              className={`w-3 h-3 rounded-full ${
                health.status === "healthy" ? "bg-green-500" : "bg-red-500"
              }`}
            />
            <span className="text-sm font-medium">
              {health.status === "healthy" ? "All systems operational" : "Backend unreachable"}
            </span>
          </div>
          {health.services && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {Object.entries(health.services).map(([key, val]) => (
                <div key={key} className="bg-gray-50 rounded p-2 text-center">
                  <div className="text-xs text-gray-500">{key.replace(/_/g, " ")}</div>
                  <div className="text-sm font-medium text-kea-700">{String(val)}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function FeatureCard({
  href,
  title,
  description,
  badge,
}: {
  href: string;
  title: string;
  description: string;
  badge: string;
}) {
  return (
    <a
      href={href}
      className="block bg-white rounded-lg shadow hover:shadow-md transition-shadow p-6 border border-gray-100"
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold text-kea-800">{title}</h3>
        <span className="text-xs font-bold bg-kea-100 text-kea-700 px-2 py-1 rounded">
          {badge}
        </span>
      </div>
      <p className="text-sm text-gray-600">{description}</p>
    </a>
  );
}
