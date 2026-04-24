"use client";

import { useState, useEffect } from "react";

export default function AssetsPage() {
  const [assets, setAssets] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchType, setSearchType] = useState("text");
  const [searchResults, setSearchResults] = useState<any>(null);
  const [typeFilter, setTypeFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [searchImage, setSearchImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string>("");

  useEffect(() => {
    fetchAssets();
  }, [typeFilter]);

  const fetchAssets = async () => {
    try {
      const params = new URLSearchParams({
        workspace_id: "demo_workspace",
      });
      if (typeFilter) params.set("type", typeFilter);
      const res = await fetch(`/api/v1/assets/?${params}`);
      if (res.ok) {
        const data = await res.json();
        setAssets(data.assets || []);
      }
    } catch (e) {
      console.error("Failed to fetch assets:", e);
    }
  };

  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSearchImage(file);
      setImagePreview(URL.createObjectURL(file));
    }
  };

  const handleSearch = async () => {
    if (searchType === "clip" || searchType === "face") {
      // Image-to-image search: upload the image file
      if (!searchImage) return;
      setLoading(true);
      try {
        const formData = new FormData();
        formData.append("image", searchImage);
        formData.append("workspace_id", "demo_workspace");
        formData.append("embed_type", searchType);
        formData.append("top_k", "10");
        const res = await fetch("/api/v1/search/similar/image", {
          method: "POST",
          body: formData,
        });
        if (res.ok) {
          setSearchResults(await res.json());
        }
      } catch (e) {
        console.error("Image search failed:", e);
      } finally {
        setLoading(false);
      }
    } else {
      // Text search
      if (!searchQuery.trim()) return;
      setLoading(true);
      try {
        const res = await fetch("/api/v1/search/similar", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: searchQuery,
            workspace_id: "demo_workspace",
            embed_type: searchType,
            top_k: 10,
          }),
        });
        if (res.ok) {
          setSearchResults(await res.json());
        }
      } catch (e) {
        console.error("Search failed:", e);
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-kea-800">Asset Library</h1>
        <p className="text-gray-600 text-sm mt-1">
          Browse generated assets and search by similarity
        </p>
      </div>

      {/* Similarity Search */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <h2 className="text-lg font-semibold mb-4">Similarity Search</h2>
        <div className="flex gap-3 flex-wrap">
          <select
            value={searchType}
            onChange={(e) => {
              setSearchType(e.target.value);
              setSearchResults(null);
            }}
            className="border rounded-md px-3 py-2 text-sm"
          >
            <option value="text">Text (Gemini Semantic)</option>
            <option value="clip">Image → Image (Gemini Vision)</option>
            <option value="face">Face Search</option>
          </select>

          {searchType === "text" ? (
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by description, style, or content..."
              className="flex-1 border rounded-md px-3 py-2 text-sm min-w-[200px]"
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            />
          ) : (
            <div className="flex-1 flex items-center gap-3 min-w-[200px]">
              <label className="flex-1 border-2 border-dashed border-gray-300 rounded-md px-3 py-2 text-sm text-gray-500 hover:border-kea-400 cursor-pointer text-center transition">
                {searchImage ? searchImage.name : "Click to upload an image..."}
                <input
                  type="file"
                  accept="image/*"
                  onChange={handleImageSelect}
                  className="hidden"
                />
              </label>
              {imagePreview && (
                <img src={imagePreview} alt="Search" className="h-10 w-10 rounded object-cover border" />
              )}
            </div>
          )}

          <button
            onClick={handleSearch}
            disabled={loading || (searchType === "text" ? !searchQuery.trim() : !searchImage)}
            className="bg-kea-600 text-white px-6 py-2 rounded-md text-sm font-medium hover:bg-kea-700 disabled:bg-gray-400"
          >
            {loading ? "Searching..." : "Search"}
          </button>
        </div>

        {searchType !== "text" && (
          <p className="text-xs text-gray-400 mt-2">
            Upload an image to find visually similar assets using Gemini Vision AI
          </p>
        )}

        {searchResults && (
          <div className="mt-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-medium text-gray-700">
                {searchResults.total_results} results in{" "}
                {searchResults.query_time_ms.toFixed(1)}ms
              </span>
              <button
                onClick={() => setSearchResults(null)}
                className="text-xs text-gray-400 hover:text-gray-600"
              >
                Clear results
              </button>
            </div>
            {searchResults.results.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {searchResults.results.map((r: any, i: number) => {
                  const meta = r.metadata || {};
                  const assetType = meta.type || "unknown";
                  const url = meta.url || "";
                  const prompt = meta.prompt || r.asset_id;
                  const provider = meta.provider || "";
                  return (
                    <div
                      key={i}
                      className="border-2 border-kea-200 rounded-lg overflow-hidden bg-white shadow-sm"
                    >
                      {/* Similarity badge */}
                      <div className="flex items-center justify-between px-3 py-1.5 bg-kea-50">
                        <span className="text-xs font-medium text-kea-700">
                          #{i + 1} Match
                        </span>
                        <div className="flex items-center gap-2">
                          <div className="w-16 bg-gray-200 rounded-full h-1.5">
                            <div
                              className="bg-kea-500 h-1.5 rounded-full"
                              style={{ width: `${r.similarity * 100}%` }}
                            />
                          </div>
                          <span className="text-xs font-bold text-kea-600">
                            {(r.similarity * 100).toFixed(1)}%
                          </span>
                        </div>
                      </div>
                      {/* Preview */}
                      {assetType === "image" && url && (
                        <div className="bg-gray-100 h-40">
                          <img
                            src={url}
                            alt={prompt}
                            className="w-full h-full object-cover"
                            onError={(e) => {
                              (e.target as HTMLImageElement).style.display = "none";
                            }}
                          />
                        </div>
                      )}
                      {assetType === "voice" && url && (
                        <div className="p-3 bg-gray-50">
                          <audio controls className="w-full h-8" src={url}>
                            Your browser does not support audio.
                          </audio>
                        </div>
                      )}
                      {assetType === "video" && (
                        <div className="p-3 bg-gray-50 flex items-center gap-2">
                          <span className="text-2xl">🎬</span>
                          <span className="text-xs text-gray-500">Video Storyboard</span>
                        </div>
                      )}
                      {/* Info */}
                      <div className="p-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs font-medium bg-gray-100 px-2 py-0.5 rounded">
                            {assetType}
                          </span>
                          <span className="text-xs text-gray-400">{provider}</span>
                        </div>
                        <p className="text-xs text-gray-600 line-clamp-2">{prompt}</p>
                        <p className="text-xs text-gray-400 mt-1 font-mono truncate">
                          {r.asset_id}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-gray-500 mt-2">
                No similar assets found. Generate some content first — assets are
                auto-indexed for search.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Asset Library */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Generated Assets</h2>
          <div className="flex space-x-2">
            {["", "image", "voice", "video"].map((t) => (
              <button
                key={t}
                onClick={() => setTypeFilter(t)}
                className={`px-3 py-1 rounded text-xs font-medium ${
                  typeFilter === t
                    ? "bg-kea-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                {t || "All"}
              </button>
            ))}
          </div>
        </div>

        {assets.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {assets.map((asset) => (
              <div
                key={asset.asset_id}
                className="border rounded-lg overflow-hidden"
              >
                {asset.type === "image" && asset.url && (
                  <div className="bg-gray-100 h-40">
                    <img
                      src={asset.url}
                      alt={asset.prompt || "Asset"}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                  </div>
                )}
                <div className="p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium bg-gray-100 px-2 py-0.5 rounded">
                      {asset.type}
                    </span>
                    <span className="text-xs text-gray-400">
                      {asset.provider}
                    </span>
                  </div>
                  <p className="text-xs text-gray-600 truncate">
                    {asset.prompt || "No prompt"}
                  </p>
                  {asset.tags?.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {asset.tags.map((t: string) => (
                        <span
                          key={t}
                          className="text-xs bg-kea-50 text-kea-600 px-1.5 py-0.5 rounded"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-12 text-gray-400">
            <p>No assets yet. Generate some content first!</p>
          </div>
        )}
      </div>
    </div>
  );
}
