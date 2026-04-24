"use client";

import { useState, useEffect } from "react";
import { generateContent, storageUrl } from "@/lib/api";

export default function GeneratePage() {
  const [form, setForm] = useState({
    type: "image" as "image" | "video" | "voice",
    prompt: "",
    style: "",
    width: 1024,
    height: 1024,
  });
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const data = await generateContent({
        type: form.type,
        prompt: form.prompt,
        style: form.style || undefined,
        dimensions:
          form.type === "image"
            ? { width: form.width, height: form.height }
            : undefined,
        user_id: "demo_user",
        workspace_id: "demo_workspace",
      });
      setResult(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-kea-800">Content Generator</h1>
        <p className="text-gray-600 text-sm mt-1">
          Multi-modal AI content generation — images, voice, and video
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Form */}
        <div className="bg-white rounded-lg shadow p-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Type Selector */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Content Type
              </label>
              <div className="flex space-x-3">
                {(["image", "voice", "video"] as const).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setForm({ ...form, type: t })}
                    className={`flex-1 py-2 rounded-md text-sm font-medium border transition ${
                      form.type === t
                        ? "bg-kea-600 text-white border-kea-600"
                        : "bg-white text-gray-700 border-gray-300 hover:border-kea-400"
                    }`}
                  >
                    {t === "image" ? "🖼 Image" : t === "voice" ? "🎤 Voice" : "🎬 Video"}
                  </button>
                ))}
              </div>
            </div>

            {/* Prompt */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {form.type === "voice" ? "Text to Speak" : "Prompt"}
              </label>
              <textarea
                value={form.prompt}
                onChange={(e) => setForm({ ...form, prompt: e.target.value })}
                rows={4}
                required
                className="w-full border rounded-md px-3 py-2 text-sm focus:ring-kea-500 focus:border-kea-500"
                placeholder={
                  form.type === "image"
                    ? "A modern SaaS dashboard with clean typography and blue accents"
                    : form.type === "voice"
                    ? "Welcome to KeaBuilder! Let us help you build amazing funnels."
                    : "A 5-second intro animation for a tech startup"
                }
              />
            </div>

            {/* Image-specific options */}
            {form.type === "image" && (
              <>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Style (optional)
                  </label>
                  <select
                    value={form.style}
                    onChange={(e) => setForm({ ...form, style: e.target.value })}
                    className="w-full border rounded-md px-3 py-2 text-sm"
                  >
                    <option value="">Default</option>
                    <option value="photorealistic">Photorealistic</option>
                    <option value="illustration">Illustration</option>
                    <option value="3d-render">3D Render</option>
                    <option value="minimalist">Minimalist</option>
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Width</label>
                    <input
                      type="number"
                      value={form.width}
                      onChange={(e) => setForm({ ...form, width: Number(e.target.value) })}
                      min={256}
                      max={2048}
                      step={64}
                      className="w-full border rounded-md px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Height</label>
                    <input
                      type="number"
                      value={form.height}
                      onChange={(e) => setForm({ ...form, height: Number(e.target.value) })}
                      min={256}
                      max={2048}
                      step={64}
                      className="w-full border rounded-md px-3 py-2 text-sm"
                    />
                  </div>
                </div>
              </>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-kea-600 text-white py-2.5 rounded-md font-medium hover:bg-kea-700 disabled:bg-gray-400"
            >
              {loading ? "Generating..." : `Generate ${form.type}`}
            </button>
          </form>
          {error && <p className="mt-3 text-red-600 text-sm">{error}</p>}
        </div>

        {/* Result */}
        <div>
          {result && (
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">Generated Content</h2>
                <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded">
                  {result.status}
                </span>
              </div>

              {form.type === "image" && result.url && (
                <div className="mb-4 rounded-lg overflow-hidden bg-gray-100">
                  <img
                    src={storageUrl(result.url)}
                    alt="Generated"
                    className="w-full h-auto"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = "none";
                    }}
                  />
                </div>
              )}

              {form.type === "voice" && result.url && (
                <div className="mb-4 p-4 rounded-lg bg-gray-50">
                  <div className="flex items-center gap-3 mb-3">
                    <span className="text-3xl">🎤</span>
                    <div>
                      <p className="font-medium text-gray-800">Audio Generated</p>
                      <p className="text-xs text-gray-500">Provider: {result.provider_used}</p>
                    </div>
                  </div>
                  {result.script && (
                    <div className="mb-3 p-3 bg-white rounded-md border border-gray-200">
                      <p className="text-xs font-medium text-gray-500 mb-1">Generated Script</p>
                      <p className="text-sm text-gray-800 leading-relaxed">{result.script}</p>
                    </div>
                  )}
                  <audio controls className="w-full" src={storageUrl(result.url)}>
                    Your browser does not support the audio element.
                  </audio>
                  <a
                    href={storageUrl(result.url)}
                    download
                    className="inline-block mt-2 text-xs text-kea-600 hover:text-kea-700 font-medium"
                  >
                    ⬇ Download MP3
                  </a>
                </div>
              )}

              {form.type === "video" && result.url && (
                <div className="mb-4 p-4 rounded-lg bg-gray-50">
                  <div className="flex items-center gap-3 mb-3">
                    <span className="text-3xl">🎬</span>
                    <div>
                      <p className="font-medium text-gray-800">Video Storyboard</p>
                      <p className="text-xs text-gray-500">Provider: {result.provider_used}</p>
                    </div>
                  </div>
                  <VideoStoryboard url={storageUrl(result.url)} />
                </div>
              )}

              <div className="space-y-2 text-sm">
                <InfoRow label="Asset ID" value={result.asset_id} />
                <InfoRow label="Provider" value={result.provider_used} />
                <InfoRow
                  label="Size"
                  value={
                    result.metadata?.size_bytes
                      ? `${(result.metadata.size_bytes / 1024).toFixed(1)} KB`
                      : "—"
                  }
                />
                {result.metadata?.dimensions && (
                  <InfoRow
                    label="Dimensions"
                    value={`${result.metadata.dimensions.width} × ${result.metadata.dimensions.height}`}
                  />
                )}
                <InfoRow label="URL" value={result.url} />
              </div>
            </div>
          )}

          {!result && !loading && (
            <div className="bg-white rounded-lg shadow p-12 text-center text-gray-400">
              <p className="text-lg">Generate content to see results</p>
              <p className="text-sm mt-1">
                Images use Hugging Face (free), voice uses edge-tts (free)
              </p>
            </div>
          )}

          {loading && (
            <div className="bg-white rounded-lg shadow p-12 text-center">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-kea-600 mb-3"></div>
              <p className="text-gray-600">Generating your {form.type}...</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-gray-500">{label}</span>
      <span className="text-gray-800 font-mono text-xs truncate max-w-xs">{value}</span>
    </div>
  );
}

function VideoStoryboard({ url }: { url: string }) {
  const [storyboard, setStoryboard] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(url)
      .then((r) => r.json())
      .then((data) => { setStoryboard(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, [url]);

  if (loading) return <p className="text-sm text-gray-500">Loading storyboard...</p>;
  if (!storyboard) return <p className="text-sm text-red-500">Failed to load storyboard</p>;

  return (
    <div className="space-y-3">
      {storyboard.title && (
        <h3 className="font-semibold text-gray-800">{storyboard.title}</h3>
      )}
      {storyboard.duration_seconds && (
        <p className="text-xs text-gray-500">Duration: {storyboard.duration_seconds}s • Mood: {storyboard.music_mood || "N/A"}</p>
      )}
      {storyboard.voiceover_script && (
        <div className="p-3 bg-white rounded-md border border-gray-200">
          <p className="text-xs font-medium text-gray-500 mb-1">Voiceover Script</p>
          <p className="text-sm text-gray-800 leading-relaxed">{storyboard.voiceover_script}</p>
        </div>
      )}
      {storyboard.scenes && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-gray-500">Scenes ({storyboard.scenes.length})</p>
          {storyboard.scenes.map((scene: any, i: number) => (
            <div key={i} className="p-2 bg-white rounded border border-gray-100 text-xs">
              <div className="flex justify-between mb-1">
                <span className="font-medium text-gray-700">Scene {scene.scene_number || i + 1}</span>
                <span className="text-gray-400">{scene.duration_seconds}s • {scene.camera_angle}</span>
              </div>
              <p className="text-gray-600">{scene.description}</p>
              {scene.visual_style && <p className="text-gray-400 mt-0.5">Style: {scene.visual_style}</p>}
            </div>
          ))}
        </div>
      )}
      {storyboard.message && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-md p-3 text-sm text-yellow-800">
          <p>{storyboard.message}</p>
        </div>
      )}
    </div>
  );
}
