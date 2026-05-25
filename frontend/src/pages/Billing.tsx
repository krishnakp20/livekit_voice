import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";

export default function Billing() {
  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Billing & Usage</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { label: "Current Plan", value: "Professional" },
          { label: "Calls This Month", value: "—" },
          { label: "Minutes Used", value: "—" },
        ].map(({ label, value }) => (
          <Card key={label}>
            <CardHeader><CardTitle className="text-base">{label}</CardTitle></CardHeader>
            <CardContent><p className="text-2xl font-bold">{value}</p></CardContent>
          </Card>
        ))}
      </div>
      <Card className="mt-6">
        <CardHeader><CardTitle>Usage History</CardTitle></CardHeader>
        <CardContent className="text-sm text-slate-500">
          Usage billing records are tracked per billing period. Connect your payment provider in Settings.
        </CardContent>
      </Card>
    </div>
  );
}
