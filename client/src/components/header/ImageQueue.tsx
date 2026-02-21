import { useState, useEffect } from 'react';
import Logo from '/logo.svg';
import { Button } from '@/components/ui/button';
import { X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

interface ImageTask {
  id: string; // random ID
  imageName: string; // main name
  satellite: string;
  location: string; // e.g., "37.7749° N, 122.4194° W"
  timestamp: string; // e.g., "2026-02-07 10:30 UTC"
  status: 'queued' | 'processing' | 'done' | 'failed';
  progress?: number;
}

// Header with full-screen Image Queue modal
export const Header = () => {
  const [isQueueOpen, setIsQueueOpen] = useState(false);

  const [imageQueue, setImageQueue] = useState<ImageTask[]>([
    {
      id: '1a2b',
      imageName: 'Ocean Scan',
      satellite: 'Sentinel-2A',
      location: '37.7749° N, 122.4194° W',
      timestamp: '2026-02-07 10:30 UTC',
      status: 'processing',
      progress: 45,
    },
    {
      id: '3c4d',
      imageName: 'Harbor Map',
      satellite: 'Landsat 8',
      location: '40.7128° N, 74.0060° W',
      timestamp: '2026-02-07 11:00 UTC',
      status: 'queued',
    },
    {
      id: '5e6f',
      imageName: 'Shipping Lanes',
      satellite: 'Sentinel-1B',
      location: '51.5074° N, 0.1278° W',
      timestamp: '2026-02-07 09:45 UTC',
      status: 'processing',
      progress: 10,
    },
  ]);

  // Simulate progress updates
  useEffect(() => {
    const interval = setInterval(() => {
      setImageQueue((q) =>
        q.map((task) => {
          if (task.status === 'processing' && task.progress! < 100) {
            return { ...task, progress: task.progress! + 5 };
          } else if (task.status === 'processing' && task.progress! >= 100) {
            return { ...task, status: 'done', progress: 100 };
          }
          return task;
        })
      );
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const pendingCount = imageQueue.filter(
    (t) => t.status === 'processing' || t.status === 'queued'
  ).length;

  return (
    <>
      {/* Navbar */}
      <header className="h-14 border-b border-border/60 bg-card backdrop-blur-sm px-2 flex items-center justify-between relative z-10">
        {/* Logo & Title */}
        <div className="flex items-center gap-2">
          <div>
            <h1 className="font-semibold text-lg tracking-tight">
              <img src={Logo} className="w-40" alt="Logo" />
            </h1>
            <p className="text-[10px] text-muted-foreground -mt-0.5">
              Maritime Domain Awareness System
            </p>
          </div>
        </div>

        {/* Right: Queue Button */}
        <div className="relative">
          <Button
            className="rounded-lg border border-border/60 bg-transparent hover:bg-muted text-white"
            onClick={() => setIsQueueOpen(true)}
          >
            Image Queue ({pendingCount})
          </Button>
        </div>
      </header>

      {/* Fullscreen Image Queue Modal */}
      {isQueueOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-card border border-border/60 rounded-lg shadow-lg w-[90%] max-w-xl max-h-[95vh] overflow-y-auto p-2 relative">
            {/* Modal Header */}
            <div className="flex justify-between items-center mb-2">
              <h3 className="text-sm font-semibold">Image Queue</h3>
              <Button
                className="rounded-lg border border-border/60 bg-transparent hover:bg-muted text-white"
                size="icon"
                onClick={() => setIsQueueOpen(false)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            {/* Queue List */}
            <ul className="space-y-2">
              {imageQueue.map((task) => (
                <li
                  key={task.id}
                  className="relative bg-muted/20 p-2 rounded border border-border/60"
                >
                  {/* Status Badge Top-Right */}
                  <div className="absolute top-5">
                    {task.status === 'done' && (
                      <Badge
                        variant="outline"
                        className="text-[10px] border-status-success text-status-success"
                      >
                        Done
                      </Badge>
                    )}
                    {task.status === 'failed' && (
                      <Badge
                        variant="outline"
                        className="text-[10px] border-status-destructive text-status-destructive"
                      >
                        Failed
                      </Badge>
                    )}
                    {task.status === 'queued' && (
                      <Badge
                        variant="outline"
                        className="text-[10px] border-muted text-muted-foreground"
                      >
                        Queued
                      </Badge>
                    )}
                    {task.status === 'processing' && (
                      <Badge
                        variant="outline"
                        className="text-[10px] border-status-warning text-status-warning"
                      >
                        Processing
                      </Badge>
                    )}
                  </div>

                  {/* Image Info */}
                  <div className="flex flex-col gap-2">
                    <span className="text-sm font-semibold">
                      {task.imageName} ({task.id})
                    </span>
                    <span className="text-xs text-muted-foreground">
                      Satellite: {task.satellite} <br />
                      Location: {task.location} <br />
                      Time: {task.timestamp}
                    </span>

                    {/* Progress bar */}
                    {task.status === 'processing' && task.progress != null && (
                      <div className="h-2 w-full bg-muted rounded mt-2 overflow-hidden">
                        <div
                          className="h-2 bg-accent transition-all"
                          style={{ width: `${task.progress}%` }}
                        />
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </>
  );
};

