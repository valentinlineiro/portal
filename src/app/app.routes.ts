import { Routes } from '@angular/router';
import { DirectoryPageComponent } from './pages/directory-page.component';
import { AppShellComponent } from './pages/app-shell.component';

export const APP_ROUTES: Routes = [
  { path: '', component: DirectoryPageComponent },
  { path: ':appId', component: AppShellComponent },
  { path: '**', redirectTo: '' }
];
