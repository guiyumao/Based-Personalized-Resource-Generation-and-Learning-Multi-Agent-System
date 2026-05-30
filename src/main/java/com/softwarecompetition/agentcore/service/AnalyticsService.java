package com.softwarecompetition.agentcore.service;

import com.softwarecompetition.agentcore.dto.AnalyticsReportDto;
import com.softwarecompetition.agentcore.dto.AnalyticsSuggestionDto;
import com.softwarecompetition.agentcore.dto.RadarChartDto;

public interface AnalyticsService {

    AnalyticsReportDto getReport(Long userId);

    RadarChartDto getRadarChartData(Long userId);

    AnalyticsSuggestionDto getSuggestion(Long userId);
}
