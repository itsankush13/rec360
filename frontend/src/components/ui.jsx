export function PageHeader({ title, subtitle, action }) {
  return (
    <div className="flex items-center justify-between mb-6">
      <div>
        <h1 className="text-xl font-semibold text-ink-900 tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-ink-500 mt-0.5">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

export function Card({ title, action, children, className = "" }) {
  return (
    <div className={`bg-surface border border-line rounded-xl p-5 ${className}`}>
      {title && (
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[13px] font-semibold text-ink-700 uppercase tracking-wide">{title}</h3>
          {action}
        </div>
      )}
      {children}
    </div>
  )
}

export function Stat({ label, value, delta, positive = true }) {
  return (
    <div className="bg-surface border border-line rounded-xl p-5">
      <p className="text-sm text-ink-500">{label}</p>
      <div className="flex items-end justify-between mt-2">
        <span className="text-2xl font-semibold text-ink-900">{value}</span>
        {delta && (
          <span className={`text-xs font-medium ${positive ? "text-good-600" : "text-bad-600"}`}>
            {positive ? "▲" : "▼"} {delta}
          </span>
        )}
      </div>
    </div>
  )
}

export function Badge({ children, className = "" }) {
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${className}`}>
      {children}
    </span>
  )
}

export function Button({ children, variant = "primary", className = "", ...props }) {
  const variants = {
    primary: "bg-brand-600 text-white hover:bg-brand-700",
    secondary: "bg-white border border-line text-ink-700 hover:bg-slate-50",
    ghost: "text-ink-500 hover:bg-slate-100",
    danger: "bg-bad-100 text-bad-600 hover:bg-red-100",
  }
  return (
    <button
      className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${variants[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

export function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-sm text-ink-700 mb-1.5">{label}</span>
      {children}
    </label>
  )
}

export const inputClass =
  "w-full border border-line rounded-lg px-3 py-2 text-sm text-ink-900 placeholder:text-ink-400 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500"
