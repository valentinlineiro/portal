import { Routes } from '@angular/router';
import { DirectoryPageComponent } from './pages/directory-page.component';

export const APP_ROUTES: Routes = [
  { path: '', component: DirectoryPageComponent },
  {
    path: 'exam-corrector',
    loadComponent: () =>
      import('../../../exam-corrector/frontend/exam-corrector-page.component')
        .then(m => m.ExamCorrectorPageComponent)
  },
  {
    path: 'attendance-checker',
    loadComponent: () =>
      import('../../../attendance-checker/frontend/attendance-checker-page.component')
        .then(m => m.AttendanceCheckerPageComponent)
  },
  { path: '**', redirectTo: '' }
];
