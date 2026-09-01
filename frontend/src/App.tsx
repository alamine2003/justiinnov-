import { Navigate, Route, Routes } from "react-router-dom"
import { AppLayout } from "@/components/layout/app-layout"
import { useAuth } from "@/context/auth"
import { CountriesPage } from "@/pages/countries/list"
import { CountryDetailPage } from "@/pages/countries/detail"
import { LoginPage } from "@/pages/login"

function Protected({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth()
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/countries"
        element={
          <Protected>
            <AppLayout />
          </Protected>
        }
      >
        <Route index element={<CountriesPage />} />
        <Route path=":id" element={<CountryDetailPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/countries" replace />} />
    </Routes>
  )
}