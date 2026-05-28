import { useEffect, useState, useRef } from "react";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Select } from "@/components/ui/Input";
import { getCampaigns, getLeads, uploadLeads } from "@/lib/api";

export default function Leads() {
  const [leads, setLeads] = useState<Record<string, unknown>[]>([]);
  const [campaigns, setCampaigns] = useState<{ id: number; name: string }[]>([]);
  const [campaignId, setCampaignId] = useState<number | "">("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => {
    const cid = campaignId === "" ? undefined : Number(campaignId);
    getLeads(cid).then((r) => setLeads(r.data));
  };

  useEffect(() => {
    getCampaigns().then((r) => setCampaigns(r.data));
  }, []);

  useEffect(() => {
    load();
  }, [campaignId]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const cid = campaignId === "" ? undefined : Number(campaignId);
      const res = await uploadLeads(file, cid);
      const imported = res.data.imported ?? 0;
      const skipped = res.data.skipped_duplicates ?? 0;
      const invalid = res.data.skipped_invalid ?? 0;

      if (imported === 0 && skipped === 0 && invalid === 0) {
        alert("⚠️ No leads found in the file. Check that your CSV has a 'phone' column and at least one data row.");
        return;
      }

      const parts: string[] = [`✅ Imported ${imported} leads.`];
      if (skipped > 0) parts.push(`${skipped} duplicates skipped.`);
      if (invalid > 0) parts.push(`${invalid} rows had invalid/missing phone numbers.`);
      alert(parts.join(" "));
      load();
    } catch (err: unknown) {
      // FastAPI can return detail as string OR as array of validation-error objects
      const detail = (err as any)?.response?.data?.detail;
      let msg: string;
      if (typeof detail === "string") {
        msg = detail;
      } else if (Array.isArray(detail)) {
        // e.g. [{loc:[...], msg:"Field required", type:"missing"}, ...]
        msg = detail.map((e: any) => e.msg ?? JSON.stringify(e)).join("; ");
      } else if (detail) {
        msg = JSON.stringify(detail);
      } else {
        msg = (err as Error)?.message ?? "Unknown error";
      }
      const status = (err as any)?.response?.status;
      alert(`❌ Upload failed (${status ?? "network error"}): ${msg}`);
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <h2 className="text-2xl font-bold">Leads</h2>
        <div className="flex items-center gap-3">
          <Select
            value={campaignId}
            onChange={(e) =>
              setCampaignId(e.target.value === "" ? "" : Number(e.target.value))
            }
          >
            <option value="">All campaigns</option>
            {campaigns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
          <input
            ref={fileRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={handleUpload}
          />
          <Button variant="secondary" onClick={() => fileRef.current?.click()}>
            <Upload className="h-4 w-4 mr-2" /> Upload CSV
          </Button>
        </div>
      </div>

      <Card className="mb-4">
        <CardContent className="py-3 text-sm text-slate-600">
          CSV columns: <span className="font-mono">phone</span> (required),{" "}
          <span className="font-mono">name</span>, <span className="font-mono">email</span> (optional).{" "}
          Campaign select karo to assign leads — ya bina campaign ke bhi upload kar sakte ho.
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b">
              <tr>
                <th className="text-left px-4 py-3">Phone</th>
                <th className="text-left px-4 py-3">Name</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="text-left px-4 py-3">Retries</th>
              </tr>
            </thead>
            <tbody>
              {leads.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-12 text-center text-slate-500">
                    No leads yet
                  </td>
                </tr>
              )}
              {leads.map((l) => (
                <tr key={l.id as number} className="border-b border-slate-50">
                  <td className="px-4 py-3 font-mono">{l.phone as string}</td>
                  <td className="px-4 py-3">{(l.name as string) || "—"}</td>
                  <td className="px-4 py-3">
                    <Badge status={l.status as string} />
                  </td>
                  <td className="px-4 py-3">{l.retry_count as number}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
