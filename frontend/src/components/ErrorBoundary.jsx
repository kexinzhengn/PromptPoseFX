import React from 'react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: 'var(--editor-bg)' }}>
          <div className="text-center">
            <span className="text-sm" style={{ color: '#c18d8d' }}>Something went wrong</span>
            <pre className="text-xs mt-2" style={{ color: 'var(--editor-muted)' }}>{this.state.error.message}</pre>
            <button
              className="mt-4 text-sm font-medium"
              style={{ color: 'var(--editor-text)' }}
              onClick={() => window.location.reload()}
            >
              Reload page
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
