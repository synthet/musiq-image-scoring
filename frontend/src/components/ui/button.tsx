import { type ButtonHTMLAttributes, type ReactNode } from 'react'
import { clsx } from 'clsx'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'outline'
  size?: 'xs' | 'sm' | 'md' | 'lg'
  children: ReactNode
  loading?: boolean
}

export function Button({
  variant = 'secondary',
  size = 'md',
  children,
  loading = false,
  disabled,
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={clsx(
        'inline-flex items-center justify-center gap-1.5 font-medium rounded-md transition-colors cursor-pointer select-none',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        size === 'xs' && 'px-2 py-0.5 text-xs',
        size === 'sm' && 'px-3 py-1 text-xs',
        size === 'md' && 'px-3.5 py-1.5 text-sm',
        size === 'lg' && 'px-4 py-2 text-sm',
        variant === 'primary' &&
          'bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] border border-[var(--color-accent-hover)]',
        variant === 'secondary' &&
          'bg-[var(--color-bg-elevated)] text-[var(--color-text-primary)] hover:bg-[var(--color-bg-elevated)] border border-[var(--color-border)]',
        variant === 'ghost' &&
          'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-elevated)]',
        variant === 'danger' &&
          'bg-[var(--color-danger)] text-white hover:bg-[var(--color-danger)] border border-[var(--color-danger-border)]',
        variant === 'outline' &&
          'text-[var(--color-accent-bright)] border border-[var(--color-accent)] hover:bg-[var(--color-accent-dim)]',
        className,
      )}
    >
      {loading && (
        <svg className="animate-spin w-3 h-3" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
        </svg>
      )}
      {children}
    </button>
  )
}
