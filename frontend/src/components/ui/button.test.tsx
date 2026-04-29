/** @vitest-environment jsdom */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Button } from './button'

describe('Button', () => {
  it('renders children and primary variant', () => {
    render(<Button variant="primary">Save</Button>)
    const btn = screen.getByRole('button', { name: 'Save' })
    expect(btn).toBeInTheDocument()
    // Primary uses the accent token; we assert the variable name, not the literal hex.
    expect(btn.className).toContain('bg-[var(--color-accent)]')
  })

  it('is disabled when loading and shows spinner', () => {
    render(
      <Button loading data-testid="busy">
        Submit
      </Button>,
    )
    const btn = screen.getByTestId('busy')
    expect(btn).toBeDisabled()
    expect(btn.querySelector('svg')).toBeTruthy()
  })

  it('calls onClick when clicked', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Go</Button>)
    await user.click(screen.getByRole('button', { name: 'Go' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })
})
