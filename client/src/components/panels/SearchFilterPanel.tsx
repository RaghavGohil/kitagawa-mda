import { useState } from 'react';
import { Search, Filter, X } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { RangeSlider } from '@/components/ui/range-slider';

import { Vessel } from '@/types';
import { vesselTypeData, anomalyTypeData } from '@/data/data';

/* ===================== TYPES ===================== */

interface SearchFilterPanelProps {
  vessels: Vessel[];
  onFilteredVessels: (vessels: Vessel[]) => void;
  onVesselSelect: (vessel: Vessel) => void;
}

const anomalyTypeOptions = [
  { value: 'dont-apply', label: 'Don\'t Apply' },
  ...Object.entries(anomalyTypeData).map(([key, data]) => ({
    value: key,
    label: data.label,
  })),
];

/* ===================== COMPONENT ===================== */

export const SearchFilterPanel = ({
  vessels,
  onFilteredVessels,
  onVesselSelect,
}: SearchFilterPanelProps) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [anomalyTypeFilter, setAnomalyTypeFilter] = useState('dont-apply');
  const [isExpanded, setIsExpanded] = useState(false);

  /* ===================== FILTER LOGIC ===================== */

  const applyFilters = () => {
    let filtered = [...vessels];

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(v =>
        v.name.toLowerCase().includes(q) ||
        v.mmsi.includes(q) ||
        (v.imo || '').toLowerCase().includes(q) ||
        (v.callSign || '').toLowerCase().includes(q)
      );
    }

    if (anomalyTypeFilter !== 'dont-apply') {
      filtered = filtered.filter(v => v.anomaly.type === anomalyTypeFilter);
    }

    onFilteredVessels(filtered);
  };

  const resetFilters = () => {
    setSearchQuery('');
    setAnomalyTypeFilter('dont-apply');
    onFilteredVessels(vessels);
  };

  const hasActiveFilters =
    searchQuery.trim() ||
    anomalyTypeFilter !== 'dont-apply';

  /* ===================== QUICK SEARCH ===================== */

  const searchResults = searchQuery.trim()
    ? vessels
      .filter(v =>
        v.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        v.mmsi.includes(searchQuery) ||
        (v.imo || '').toLowerCase().includes(searchQuery.toLowerCase())
      )
      .slice(0, 5)
    : [];

  /* ===================== RENDER ===================== */

  return (
    <div className="rounded-lg border border-border/60 bg-card/95 backdrop-blur">
      {/* Search Bar */}
      <div className="p-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by name, MMSI, IMO..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="pl-9 pr-9 bg-muted/50 border-border"
          />
          {searchQuery && (
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7"
              onClick={() => setSearchQuery('')}
            >
              <X className="h-3 w-3" />
            </Button>
          )}
        </div>

        {searchResults.length > 0 && (
          <div className="mt-2 space-y-1">
            {searchResults.map(vessel => {
              const anomalyMeta = vessel.type === 'ship' ? undefined : (vessel.anomaly.type === 'anomaly' ? anomalyTypeData['anomaly'] : anomalyTypeData['unidentified']);

              return (
                <button
                  key={vessel.id}
                  className="w-full text-left px-2 py-1.5 rounded hover:bg-accent transition-colors flex justify-between"
                  onClick={() => {
                    onVesselSelect(vessel);
                    setSearchQuery('');
                  }}
                >
                  <div>
                    <div className="text-sm">{vessel.name}</div>
                    <div className="text-xs text-muted-foreground font-mono">
                      {vessel.mmsi}
                    </div>
                  </div>

                  {vessel.type === 'unidentified' && (
                    <Badge
                      variant="outline"
                      className="text-[10px]"
                      style={{
                        borderColor: anomalyMeta?.color ?? '#FACC15',
                        color: anomalyMeta?.color ?? '#FACC15',
                      }}
                    >
                      {anomalyMeta?.label ?? 'Unidentified'}
                    </Badge>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Filters Toggle */}
      <div className="px-2 pb-2">
        <Button
          size="sm"
          className="w-full justify-between border border-border/60 bg-transparent hover:bg-muted text-white"
          onClick={() => setIsExpanded(v => !v)}
        >
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4" />
            <span>Filters</span>
            {hasActiveFilters && (
              <Badge className="text-xs border border-border/60 bg-transparent text-muted-foreground">
                Active
              </Badge>
            )}
          </div>
        </Button>
      </div>

      {/* Expanded Filters */}
      {isExpanded && (
        <div className="border-t border-border px-2 py-2 space-y-2">
          {/* Anomaly Type / Classification */}
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Vessel Classification</label>
            <Select value={anomalyTypeFilter} onValueChange={setAnomalyTypeFilter}>
              <SelectTrigger className="bg-muted/50">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {anomalyTypeOptions.map(v => (
                  <SelectItem key={v.value} value={v.value}>
                    {v.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>


          {/* Actions */}
          <div className="flex gap-2 pt-1">
            <Button
              size="sm"
              className="flex-1 border border-border/60 bg-transparent hover:bg-muted text-white"
              onClick={resetFilters}
            >
              Reset
            </Button>
            <Button
              size="sm"
              className="flex-1 border border-border/60 bg-transparent hover:bg-muted text-white"
              onClick={applyFilters}
            >
              Apply
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

