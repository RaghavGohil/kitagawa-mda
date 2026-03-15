"use client";

import { useState } from "react";
import { Search, SlidersHorizontal, X, ChevronRight } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Vessel } from "@/types";
import { anomalyTypeData } from "@/data/data";

interface SearchFilterPanelProps {
    vessels: Vessel[];
    onFilteredVessels: (vessels: Vessel[]) => void;
    onVesselSelect: (vessel: Vessel) => void;
    isDocked?: boolean;
}

const anomalyTypeOptions = [
    { value: "all", label: "All vessels" },
    ...Object.entries(anomalyTypeData).map(([key, data]) => ({ value: key, label: data.label })),
];

export const SearchFilterPanel = ({ vessels, onFilteredVessels, onVesselSelect, isDocked }: SearchFilterPanelProps) => {
    const [searchQuery, setSearchQuery] = useState("");
    const [anomalyTypeFilter, setAnomalyTypeFilter] = useState("all");
    const [showFilters, setShowFilters] = useState(false);

    const applyFilters = () => {
        let filtered = [...vessels];
        if (searchQuery.trim()) {
            const q = searchQuery.toLowerCase();
            filtered = filtered.filter(v =>
                v.name.toLowerCase().includes(q) || v.mmsi.includes(q) ||
                (v.imo || "").toLowerCase().includes(q) || (v.callSign || "").toLowerCase().includes(q),
            );
        }
        if (anomalyTypeFilter !== "all") {
            filtered = filtered.filter(v => v.anomaly.type === anomalyTypeFilter);
        }
        onFilteredVessels(filtered);
    };

    const searchResults = searchQuery.trim()
        ? vessels.filter(v =>
            v.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            v.mmsi.includes(searchQuery),
        ).slice(0, 5)
        : [];

    return (
        <div className={cn(isDocked && "space-y-3")}>
            {/* Search Row */}
            <div className="flex gap-2 min-w-0">
                <div className="relative flex-1 min-w-0">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                        placeholder="Search vessels…"
                        value={searchQuery}
                        onChange={e => setSearchQuery(e.target.value)}
                        className="pl-10 h-10 w-full"
                    />
                    {searchQuery && (
                        <button className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground" onClick={() => setSearchQuery("")}>
                            <X className="h-4 w-4" />
                        </button>
                    )}
                </div>
                <Button
                    variant={showFilters ? "secondary" : "outline"}
                    size="icon"
                    className="h-10 w-10 shrink-0"
                    onClick={() => setShowFilters(v => !v)}
                    title="Filters"
                >
                    <SlidersHorizontal className="h-4 w-4" />
                </Button>
            </div>

            {/* Search Results */}
            {searchResults.length > 0 && (
                <div className="rounded-lg border border-border divide-y divide-border">
                    {searchResults.map(vessel => (
                        <Button
                            key={vessel.id}
                            variant="ghost"
                            className="w-full justify-between h-auto py-3 px-4 rounded-none first:rounded-t-lg last:rounded-b-lg"
                            onClick={() => { onVesselSelect(vessel); setSearchQuery(""); }}
                        >
                            <div className="min-w-0 text-left">
                                <p className="text-sm font-medium truncate">{vessel.name}</p>
                                <p className="text-xs text-muted-foreground mt-0.5">{vessel.mmsi || "No MMSI"}</p>
                            </div>
                            <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0 ml-2" />
                        </Button>
                    ))}
                </div>
            )}

            {/* Filters */}
            {showFilters && (
                <div className="rounded-lg border border-border p-4 space-y-4">
                    <h4 className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Filters</h4>
                    <div className="space-y-2">
                        <label className="text-sm text-muted-foreground">Vessel Type</label>
                        <Select value={anomalyTypeFilter} onValueChange={(v) => { if (v) setAnomalyTypeFilter(v); }}>
                            <SelectTrigger className="h-10 w-full">
                                <SelectValue placeholder="All vessels" />
                            </SelectTrigger>
                            <SelectContent>
                                {anomalyTypeOptions.map(v => (
                                    <SelectItem key={v.value} value={v.value}>{v.label}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <Button className="w-full h-10" onClick={applyFilters}>Apply Filters</Button>
                </div>
            )}
        </div>
    );
};
