import { useCallback, useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Bell, CheckCheck, Loader2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { FormError } from "@/components/ui/form-error"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import {
  fetchNotifications,
  fetchUnreadCount,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/lib/reporting"
import { notificationKindIcon } from "@/lib/labels"
import type { AlertLevel, AppNotification } from "@/lib/types"
import { cn, formatDate } from "@/lib/utils"

const LEVEL_DOT: Record<AlertLevel, string> = {
  info: "bg-statut-info",
  warning: "bg-statut-attente",
  critical: "bg-destructive",
}

/** Intervalle de rafraîchissement du compteur, en millisecondes. */
const POLL_INTERVAL = 60_000

export function NotificationBell() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [unread, setUnread] = useState(0)
  const [items, setItems] = useState<AppNotification[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refreshCount = useCallback(async () => {
    try {
      const { unread: count } = await fetchUnreadCount()
      setUnread(count)
    } catch {
      // Un compteur indisponible ne doit pas perturber la navigation.
    }
  }, [])

  useEffect(() => {
    // Un onglet en arrière-plan n'a pas besoin de compter ses notifications :
    // vingt onglets ouverts interrogeaient le serveur toutes les minutes
    // chacun. Le compteur se remet à jour au retour.
    let active = true
    let timer: number | null = null
    const poll = () => {
      fetchUnreadCount()
        .then(({ unread: count }) => {
          if (active) setUnread(count)
        })
        .catch(() => {
          // Voir `refreshCount`.
        })
    }
    const start = () => {
      if (timer !== null) return
      timer = window.setInterval(poll, POLL_INTERVAL)
    }
    const stop = () => {
      if (timer === null) return
      window.clearInterval(timer)
      timer = null
    }
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        poll()
        start()
      } else {
        stop()
      }
    }
    poll()
    if (document.visibilityState === "visible") start()
    document.addEventListener("visibilitychange", onVisibility)
    return () => {
      active = false
      stop()
      document.removeEventListener("visibilitychange", onVisibility)
    }
  }, [])

  const loadItems = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const page = await fetchNotifications({ page_size: 30 })
      setItems(page.results)
    } catch (e) {
      setError(e instanceof Error ? e.message : t("notifications.indisponibles"))
    } finally {
      setLoading(false)
    }
  }, [t])

  const openPanel = async () => {
    setOpen(true)
    await loadItems()
  }

  const handleClick = async (notification: AppNotification) => {
    setError(null)
    try {
      if (!notification.read_at) {
        await markNotificationRead(notification.id)
        await Promise.all([loadItems(), refreshCount()])
      }
      if (notification.link) {
        setOpen(false)
        navigate(notification.link)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("erreurs.action_impossible"))
    }
  }

  const markAll = async () => {
    setError(null)
    try {
      await markAllNotificationsRead()
      await Promise.all([loadItems(), refreshCount()])
    } catch (e) {
      setError(e instanceof Error ? e.message : t("erreurs.action_impossible"))
    }
  }

  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        aria-label={unread ? t("notifications.aria_non_lues", { count: unread }) : t("notifications.aria")}
        className="relative"
        onClick={() => void openPanel()}
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-destructive-foreground">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </Button>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-md">
          <SheetHeader>
            <SheetTitle>{t("notifications.titre")}</SheetTitle>
            <SheetDescription>{t("notifications.description")}</SheetDescription>
          </SheetHeader>

          <div className="mt-4 space-y-3 px-4 pb-6">
            <FormError>{error}</FormError>

            {unread > 0 && (
              <Button variant="outline" size="sm" onClick={() => void markAll()}>
                <CheckCheck className="mr-1 h-4 w-4" aria-hidden />
                {t("notifications.tout_lu")}
              </Button>
            )}

            {loading ? (
              <div className="flex h-24 items-center justify-center" aria-busy="true">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : items.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                {t("notifications.aucune")}
              </p>
            ) : (
              items.map((notification) => {
                const KindIcon = notificationKindIcon(notification.kind)
                return (
                  <button
                    key={notification.id}
                    type="button"
                    aria-label={notification.title}
                    onClick={() => void handleClick(notification)}
                    className={cn(
                      "w-full rounded-lg border border-border/60 p-3 text-left transition-colors hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      !notification.read_at && "bg-accent/20",
                    )}
                  >
                    <div className="flex items-start gap-2">
                      <span
                        aria-hidden
                        className={cn(
                          "mt-1.5 h-2 w-2 shrink-0 rounded-full",
                          LEVEL_DOT[notification.level],
                          notification.read_at && "opacity-30",
                        )}
                      />
                      <div className="min-w-0 flex-1">
                        <p className="flex items-center gap-1.5 text-sm font-medium">
                          {KindIcon && (
                            <KindIcon
                              className="h-3.5 w-3.5 shrink-0 text-muted-foreground"
                              aria-label={notification.kind_display}
                            />
                          )}
                          {notification.title}
                        </p>
                        {notification.body && (
                          <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                            {notification.body}
                          </p>
                        )}
                        <div className="mt-1 flex items-center gap-2">
                          <span className="text-xs text-muted-foreground">
                            {formatDate(notification.created_at)}
                          </span>
                          {notification.country_name && (
                            <Badge variant="secondary" className="text-[10px]">
                              {notification.country_name}
                            </Badge>
                          )}
                        </div>
                      </div>
                    </div>
                  </button>
                )
              })
            )}
          </div>
        </SheetContent>
      </Sheet>
    </>
  )
}
