import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AppRegistryService } from '../services/app-registry.service';

@Component({
  selector: 'app-directory-page',
  standalone: true,
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <main class="layout">
      <header class="topbar">
        <h1>~/apps</h1>
        <button class="logout" type="button" (click)="logout()">Logout</button>
      </header>
      <p class="subtitle">Directorio de aplicaciones</p>
      @for (app of registry.apps.value() ?? []; track app.id) {
        @if (app.status !== 'disabled') {
          <a class="card" [routerLink]="'/' + app.route" [class.wip]="app.status === 'wip'">
            <h2>{{ app.icon }} {{ app.name }}</h2>
            <p>{{ app.description }}</p>
          </a>
        }
      }
      @if (registry.apps.isLoading()) {
        <p class="loading">Cargando...</p>
      }
    </main>
  `,
  styles: [`
    .layout { max-width: 900px; margin: 0 auto; padding: 28px; }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    h1 { font-size: 20px; margin: 0; }
    .subtitle { color: #888; margin: 8px 0 16px; }
    .card {
      display: block;
      border: 1px solid #2a2a2a;
      background: #141414;
      padding: 16px;
      color: #e8e8e8;
      text-decoration: none;
      max-width: 420px;
      margin-bottom: 12px;
    }
    .card.wip { opacity: 0.6; }
    .card h2 { margin: 0 0 8px; font-size: 16px; }
    .card p { margin: 0; color: #999; font-size: 14px; }
    .loading { color: #666; }
    .logout {
      border: 1px solid #333;
      background: #191919;
      color: #ddd;
      padding: 8px 12px;
      cursor: pointer;
    }
  `]
})
export class DirectoryPageComponent {
  registry = inject(AppRegistryService);

  async logout() {
    sessionStorage.removeItem('portal_login_attempted');
    window.location.assign('/auth/logout?next=%2F');
  }
}
