import { Component, type ReactNode } from 'react'

interface Props { children: ReactNode; fallback?: ReactNode }

interface State { hasError: boolean; error?: Error }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="panel" style={{ padding: 24, textAlign: 'center' }}>
          <h3 style={{ color: 'var(--rog-red)', margin: '0 0 8px' }}>Something went wrong</h3>
          <p style={{ color: 'var(--text)', fontSize: 13, opacity: 0.7, margin: '0 0 12px' }}>
            {this.state.error?.message ?? 'An unexpected error occurred.'}
          </p>
          <button
            className="btn-secondary"
            onClick={() => this.setState({ hasError: false, error: undefined })}
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
