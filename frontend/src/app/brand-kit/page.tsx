"use client";

import { useState } from "react";
import { API_BASE } from "@/lib/api";

export default function BrandKitPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [loraName, setLoraName] = useState("");
  const [triggerToken, setTriggerToken] = useState("ohwx person");
  const [steps, setSteps] = useState(1500);
  const [trainResult, setTrainResult] = useState<any>(null);
  const [generatePrompt, setGeneratePrompt] = useState("");
  const [genResult, setGenResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleTrain = async (e: React.FormEvent) => {
    e.preventDefault();
    if (files.length < 5) {
      setError("Please upload at least 5 reference images");
      return;
    }
    setLoading(true);
    setError("");

    const formData = new FormData();
    formData.append("user_id", "demo_user");
    formData.append("workspace_id", "demo_workspace");
    formData.append("lora_name", loraName);
    formData.append("trigger_token", triggerToken);
    formData.append("training_steps", String(steps));
    files.forEach((f) => formData.append("images", f));

    try {
      const res = await fetch(`${API_BASE}/lora/train`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Error: ${res.status}`);
      }
      setTrainResult(await res.json());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async () => {
    if (!trainResult?.lora_id || !generatePrompt) return;
    setLoading(true);
    setError("");

    try {
      const res = await fetch(`${API_BASE}/lora/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: "demo_user",
          workspace_id: "demo_workspace",
          lora_id: trainResult.lora_id,
          prompt: generatePrompt,
          use_brand_style: true,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Error: ${res.status}`);
      }
      setGenResult(await res.json());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-kea-800">Brand Kit (LoRA)</h1>
        <p className="text-gray-600 text-sm mt-1">
          Train a personalised AI model on your brand. Upload reference images to get started.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Training */}
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold mb-4">1. Train Brand Model</h2>
            <form onSubmit={handleTrain} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Brand Style Name
                </label>
                <input
                  type="text"
                  value={loraName}
                  onChange={(e) => setLoraName(e.target.value)}
                  required
                  placeholder="e.g. My Company Brand"
                  className="w-full border rounded-md px-3 py-2 text-sm"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Reference Images (5–30)
                </label>
                <input
                  type="file"
                  multiple
                  accept="image/*"
                  onChange={(e) => setFiles(Array.from(e.target.files || []))}
                  className="w-full border rounded-md px-3 py-2 text-sm"
                />
                {files.length > 0 && (
                  <p className="text-xs text-gray-500 mt-1">
                    {files.length} image(s) selected
                  </p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Trigger Token
                  </label>
                  <input
                    type="text"
                    value={triggerToken}
                    onChange={(e) => setTriggerToken(e.target.value)}
                    className="w-full border rounded-md px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Training Steps
                  </label>
                  <input
                    type="number"
                    value={steps}
                    onChange={(e) => setSteps(Number(e.target.value))}
                    min={500}
                    max={5000}
                    className="w-full border rounded-md px-3 py-2 text-sm"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full bg-kea-600 text-white py-2.5 rounded-md font-medium hover:bg-kea-700 disabled:bg-gray-400"
              >
                {loading ? "Training..." : "Start Training"}
              </button>
            </form>
          </div>

          {trainResult && (
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-3">Training Result</h2>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">LoRA ID</span>
                  <span className="font-mono">{trainResult.lora_id}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Status</span>
                  <span
                    className={`font-medium ${
                      trainResult.status === "ready"
                        ? "text-green-600"
                        : "text-yellow-600"
                    }`}
                  >
                    {trainResult.status}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Generation */}
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold mb-4">2. Generate with Brand Style</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Image Prompt
                </label>
                <textarea
                  value={generatePrompt}
                  onChange={(e) => setGeneratePrompt(e.target.value)}
                  rows={3}
                  className="w-full border rounded-md px-3 py-2 text-sm"
                  placeholder="A professional headshot in a modern office setting"
                />
              </div>

              <button
                onClick={handleGenerate}
                disabled={loading || !trainResult?.lora_id}
                className="w-full bg-kea-600 text-white py-2.5 rounded-md font-medium hover:bg-kea-700 disabled:bg-gray-400"
              >
                {!trainResult?.lora_id
                  ? "Train a model first"
                  : loading
                  ? "Generating..."
                  : "Generate with Brand Style"}
              </button>
            </div>
          </div>

          {genResult && (
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-3">Generated Image</h2>
              {genResult.url && (
                <div className="mb-3 rounded-lg overflow-hidden bg-gray-100">
                  <img
                    src={genResult.url}
                    alt="LoRA generated"
                    className="w-full h-auto"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = "none";
                    }}
                  />
                </div>
              )}
              <div className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Prompt Used</span>
                  <span className="text-xs truncate max-w-[200px]">
                    {genResult.prompt_used}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">LoRA</span>
                  <span className="font-mono text-xs">{genResult.lora_id}</span>
                </div>
              </div>
            </div>
          )}

          {error && <p className="text-red-600 text-sm">{error}</p>}

          <div className="bg-blue-50 rounded-lg p-4 text-sm text-blue-800">
            <strong>How it works:</strong>
            <ol className="list-decimal list-inside mt-2 space-y-1">
              <li>Upload 10–20 reference images of your brand/face</li>
              <li>AI trains a LoRA adapter (~10-15 min on GPU)</li>
              <li>Generate consistent branded images using your prompt</li>
              <li>Toggle "Brand Style" on/off in the builder</li>
            </ol>
          </div>
        </div>
      </div>
    </div>
  );
}
