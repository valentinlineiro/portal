import { Component, CUSTOM_ELEMENTS_SCHEMA, OnInit, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  template: `
    @if (checkingAuth()) {
      <p class="status">Checking session...</p>
    } @else if (!authenticated()) {
      <main class="status">
        <p>Not logged in.</p>
        <a class="retry" [href]="loginHref()">Login</a>
      </main>
    } @else if (authError()) {
      <main class="status">
        <p>{{ authError() }}</p>
        <a class="retry" href="/auth/login?next=%2F">Retry login</a>
      </main>
    } @else {
      <router-outlet></router-outlet>
    }
  `,
  styles: [`
    .status {
      margin: 40px auto;
      max-width: 900px;
      color: #888;
      font-size: 14px;
      padding: 0 28px;
    }
    .retry { color: #e8e8e8; }
  `]
})
export class AppComponent implements OnInit {
  private static readonly LOGIN_ATTEMPT_KEY = 'portal_login_attempted';
  checkingAuth = signal(true);
  authenticated = signal(false);
  authError = signal('');

  async ngOnInit() {
    try {
      const res = await fetch('/auth/me', { credentials: 'include' });
      if (res.ok) {
        sessionStorage.removeItem(AppComponent.LOGIN_ATTEMPT_KEY);
        this.authenticated.set(true);
      }
      if (res.status === 401) {
        if (sessionStorage.getItem(AppComponent.LOGIN_ATTEMPT_KEY)) {
          this.authError.set('Login failed. Please try again.');
        } else {
          this.redirectToLogin();
          return;
        }
      }
    } catch {
      // Leave the app usable if auth endpoint is temporarily unavailable.
    }
    this.checkingAuth.set(false);
  }

  loginHref(): string {
    const next = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    return `/auth/login?next=${encodeURIComponent(next || '/')}`;
  }

  private redirectToLogin() {
    if (window.location.pathname.startsWith('/auth/')) return;
    sessionStorage.setItem(AppComponent.LOGIN_ATTEMPT_KEY, '1');
    const next = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    const nextWithMarker = this.withLoginAttemptMarker(next || '/');
    window.location.assign(`/auth/login?next=${encodeURIComponent(nextWithMarker)}`);
  }

  private withLoginAttemptMarker(next: string): string {
    const [pathAndQuery, hash = ''] = next.split('#', 2);
    const [path, query = ''] = pathAndQuery.split('?', 2);
    const params = new URLSearchParams(query);
    params.set('login_attempted', '1');
    const queryString = params.toString();
    const hashPart = hash ? `#${hash}` : '';
    return `${path}${queryString ? `?${queryString}` : ''}${hashPart}`;
  }
}
