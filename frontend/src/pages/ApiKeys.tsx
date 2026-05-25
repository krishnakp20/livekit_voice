import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

export default function ApiKeys() {
  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">API Keys</h2>
      <Card>
        <CardHeader className="flex flex-row justify-between">
          <CardTitle>Programmatic Access</CardTitle>
          <Button size="sm">Generate Key</Button>
        </CardHeader>
        <CardContent className="text-sm text-slate-500">
          API keys allow external systems to trigger calls, sync leads, and receive webhooks.
          Keys are scoped per client and support RBAC permissions.
        </CardContent>
      </Card>
    </div>
  );
}
