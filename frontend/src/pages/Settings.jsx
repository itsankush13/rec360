import { PageHeader, Card, Field, Button, inputClass } from "../components/ui"

export default function Settings() {
  return (
    <div>
      <PageHeader title="Settings" subtitle="Organization and account preferences" />
      <Card title="Organization">
        <div className="grid grid-cols-2 gap-5 max-w-xl">
          <Field label="Company Name">
            <input className={inputClass} defaultValue="Your Company" />
          </Field>
          <Field label="Support Email">
            <input className={inputClass} defaultValue="hr@yourcompany.com" />
          </Field>
        </div>
        <Button className="mt-5">Save Changes</Button>
      </Card>
    </div>
  )
}
