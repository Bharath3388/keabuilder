"use client";

import { useState } from "react";

interface ClassificationResult {
  lead_id: string;
  classification: string;
  confidence: number;
  reasoning: string;
  missing_signals: string[];
  follow_up_questions: string[];
  suggested_response: string;
  crm_tags: string[];
  next_action: string;
}

export default function LeadsPage() {
  const [form, setForm] = useState({
    name: "",
    email: "",
    company: "",
    company_size: "",
    budget_range: "",
    timeline: "",
    use_case: "",
    phone: "",
    industry: "",
  });
  const [result, setResult] = useState<ClassificationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const res = await fetch("/api/v1/leads/classify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Error: ${res.status}`);
      }
      setResult(await res.json());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const fillSample = () => {
    setForm({
      name: "Priya Sharma",
      email: "priya@techventures.in",
      company: "TechVentures",
      company_size: "75",
      budget_range: "$5,000–$10,000/month",
      timeline: "Within 30 days",
      use_case:
        "We need automated lead nurturing funnels for our SaaS product. Currently losing leads after the trial sign-up.",
      phone: "+91-9876543210",
      industry: "SaaS",
    });
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-kea-800">Lead Intelligence</h1>
          <p className="text-gray-600 text-sm mt-1">
            AI-powered lead classification and personalised response generation
          </p>
        </div>
        <button
          onClick={fillSample}
          className="text-sm bg-kea-100 text-kea-700 px-3 py-1.5 rounded hover:bg-kea-200"
        >
          Fill Sample Data
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Form */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4">Lead Form Submission</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <Input label="Name *" value={form.name} onChange={(v) => setForm({ ...form, name: v })} required />
              <Input label="Email *" value={form.email} onChange={(v) => setForm({ ...form, email: v })} type="email" required />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Input label="Company" value={form.company} onChange={(v) => setForm({ ...form, company: v })} />
              <Input label="Company Size" value={form.company_size} onChange={(v) => setForm({ ...form, company_size: v })} placeholder="e.g. 75" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Input label="Budget Range" value={form.budget_range} onChange={(v) => setForm({ ...form, budget_range: v })} placeholder="e.g. $5,000/month" />
              <Input label="Timeline" value={form.timeline} onChange={(v) => setForm({ ...form, timeline: v })} placeholder="e.g. Within 30 days" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Input label="Phone" value={form.phone} onChange={(v) => setForm({ ...form, phone: v })} />
              <Input label="Industry" value={form.industry} onChange={(v) => setForm({ ...form, industry: v })} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Use Case</label>
              <textarea
                value={form.use_case}
                onChange={(e) => setForm({ ...form, use_case: e.target.value })}
                rows={3}
                className="w-full border rounded-md px-3 py-2 text-sm focus:ring-kea-500 focus:border-kea-500"
                placeholder="Describe your needs..."
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-kea-600 text-white py-2.5 rounded-md font-medium hover:bg-kea-700 disabled:bg-gray-400"
            >
              {loading ? "Analyzing..." : "Classify & Generate Response"}
            </button>
          </form>
          {error && <p className="mt-3 text-red-600 text-sm">{error}</p>}
        </div>

        {/* Results */}
        <div className="space-y-4">
          {result && (
            <>
              {/* Classification Badge */}
              <div className="bg-white rounded-lg shadow p-6">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-lg font-semibold">Classification</h2>
                  <span className="text-xs text-gray-500">{result.lead_id}</span>
                </div>
                <div className="flex items-center space-x-4">
                  <span
                    className={`text-2xl font-bold px-4 py-2 rounded-lg ${
                      result.classification === "HOT"
                        ? "bg-red-100 text-red-700"
                        : result.classification === "WARM"
                        ? "bg-yellow-100 text-yellow-700"
                        : "bg-blue-100 text-blue-700"
                    }`}
                  >
                    {result.classification}
                  </span>
                  <div>
                    <div className="text-sm text-gray-600">
                      Confidence: <strong>{(result.confidence * 100).toFixed(0)}%</strong>
                    </div>
                    <div className="text-sm text-gray-600">
                      Next: <strong>{result.next_action.replace(/_/g, " ")}</strong>
                    </div>
                  </div>
                </div>
                <p className="mt-3 text-sm text-gray-600">{result.reasoning}</p>
              </div>

              {/* Suggested Response */}
              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="text-lg font-semibold mb-3">AI-Generated Response</h2>
                <div className="bg-gray-50 rounded-lg p-4 text-sm leading-relaxed">
                  {result.suggested_response}
                </div>
              </div>

              {/* Tags & Signals */}
              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="text-lg font-semibold mb-3">CRM Tags & Signals</h2>
                <div className="flex flex-wrap gap-2 mb-3">
                  {result.crm_tags.map((tag) => (
                    <span key={tag} className="bg-kea-100 text-kea-700 text-xs px-2 py-1 rounded">
                      {tag}
                    </span>
                  ))}
                </div>
                {result.missing_signals.length > 0 && (
                  <div className="text-sm text-amber-600">
                    Missing signals: {result.missing_signals.join(", ")}
                  </div>
                )}
                {result.follow_up_questions.length > 0 && (
                  <div className="mt-2">
                    <div className="text-sm font-medium text-gray-700">Follow-up questions:</div>
                    <ul className="list-disc list-inside text-sm text-gray-600">
                      {result.follow_up_questions.map((q, i) => (
                        <li key={i}>{q}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </>
          )}

          {!result && !loading && (
            <div className="bg-white rounded-lg shadow p-12 text-center text-gray-400">
              <p className="text-lg">Submit a lead to see AI classification results</p>
              <p className="text-sm mt-1">Try the sample data button above</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        className="w-full border rounded-md px-3 py-2 text-sm focus:ring-kea-500 focus:border-kea-500"
      />
    </div>
  );
}
