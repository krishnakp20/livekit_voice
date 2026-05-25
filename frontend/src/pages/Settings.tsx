import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/context/AuthContext";

export default function Settings() {
  const { user } = useAuth();

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Settings</h2>
      <div className="grid gap-6 max-w-2xl">
        <Card>
          <CardHeader><CardTitle>Profile</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="text-sm font-medium">Name</label>
              <Input defaultValue={user?.full_name} readOnly />
            </div>
            <div>
              <label className="text-sm font-medium">Email</label>
              <Input defaultValue={user?.email} readOnly />
            </div>
            <div>
              <label className="text-sm font-medium">Role</label>
              <Input defaultValue={user?.role} readOnly />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Notifications</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" defaultChecked /> WhatsApp call summaries
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" defaultChecked /> Missed call alerts
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" defaultChecked /> Daily reports
            </label>
            <Button className="mt-2">Save Preferences</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
