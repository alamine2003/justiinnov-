import { useCallback, useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Bell, CheckCheck, Loader2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
import type { AlertLevel, AppNotification } from "@/lib/types"
import { cn, formatDate } from "@/lib/utils"

const LEVEL_DOT: Record<AlertLevel, string> = {
  info: "bg-blue-500",
  warning: "bg-amber-500",
  critical: "bg-destructive",
}

/** Intervalle de rafraîchissement du compteur, en millisecondes. */
const POLL_INTERVAL = 60_000

export function NotificationBell() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [unread, setUnread] = useState(0)
  const [items, setItems] = useState<AppNotification[]>([])
  const [loading, setLoading] = useState(false)

  const refreshCount = useCallback(async () => {
    try {
      const { unread: count } = await fetchUnreadCount()
      setUnread(count)
    } catch {
      // Un compteur indisponible ne doit pas perturber la navigation.
    }
  }, [])

  useEffect(() => {
    void refreshCount()
    const timer = window.setInterval(refreshCount, POLL_INTERVAL)
    return () => window.clearInterval(timer)
  }, [refreshCount])

  const loadItems = useCallback(async () => {
    setLoading(true)
    try {
      const page = await fetchNotifications({ page_size: 30 })
      setItems(page.results)
    } finally {
      setLoading(false)
    }
  }, [])

  const openPanel = async () => {
    setOpen(true)
    await loadItems()
  }

  const handleClick = async (notification: AppNotification) => {
    if (!notification.read_at) {
      await markNotificationRead(notification.id)
      await Promise.all([loadItems(), refreshCount()])
    }
    if (notification.link) {
      setOpen(false)
      navigate(notification.link)
    }
  }

  const markAll = async () => {
    await markAllNotificationsRead()
    await Promise.all([loadItems(), refreshCount()])
  }

  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        aria-label={`Notifications${unread ? ` (${unread} non lues)` : ""}`}
        className="relative"
        onClick={openPanel}
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
            <SheetTitle>Notifications</SheetTitle>
            <SheetDescription>
              Seuils budgétaires, dépenses à contrôler et décisions vous
              concernant.
            </SheetDescription>
          </SheetHeader>

          <div className="mt-4 space-y-3 px-4 pb-6">
            {unread > 0 && (
              <Button variant="outline" size="sm" onClick={markAll}>
                <CheckCheck className="mr-1 h-4 w-4" />
                Tout marquer comme lu
              </Button>
            )}

            {loading ? (
              <div className="flex h-24 items-center justify-center">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : items.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                Aucune notification.
              </p>
            ) : (
              items.map((notification) => (
                <button
                  key={notification.id}
                  onClick={() => handleClick(notification)}
                  className={cn(
                    "w-full rounded-lg border border-border/60 p-3 text-left transition-colors hover:bg-accent/40",
                    !notification.read_at && "bg-accent/20",
                  )}
                >
                  <div className="flex items-start gap-2">
                    <span
                      className={cn(
                        "mt-1.5 h-2 w-2 shrink-0 rounded-full",
                        LEVEL_DOT[notification.level],
                        notification.read_at && "opacity-30",
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">{notification.title}</p>
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
              ))
            )}
          </div>
        </SheetContent>
      </Sheet>
    </>
  )
}
