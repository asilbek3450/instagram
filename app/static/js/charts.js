// Chart.js helper wrappers for Instagram Analytics Pro

const ChartThemeHelper = {
    // Determine colors based on active theme
    getThemeColors() {
        const isDark = document.querySelector('meta[name="color-scheme"]').content === 'dark';
        
        return {
            text: isDark ? '#94a3b8' : '#64748b',
            grid: isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.05)',
            primary: isDark ? '#a855f7' : '#8b5cf6', // Violet
            secondary: isDark ? '#ec4899' : '#db2777', // Pink
            success: '#10b981',
            warning: '#f59e0b',
            info: '#06b6d4',
            tooltipBg: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255, 255, 255, 0.9)',
            tooltipBorder: isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)'
        };
    },

    // Default options for Chart.js
    getCommonOptions(colors) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: {
                        color: colors.text,
                        font: { family: 'Inter', size: 12, weight: 500 }
                    }
                },
                tooltip: {
                    backgroundColor: colors.tooltipBg,
                    titleColor: colors.text,
                    bodyColor: colors.text,
                    borderColor: colors.tooltipBorder,
                    borderWidth: 1,
                    padding: 12,
                    cornerRadius: 8,
                    titleFont: { family: 'Outfit', size: 14, weight: 600 },
                    bodyFont: { family: 'Inter', size: 13 }
                }
            },
            scales: {
                x: {
                    grid: { color: colors.grid },
                    ticks: {
                        color: colors.text,
                        font: { family: 'Inter', size: 11 }
                    }
                },
                y: {
                    grid: { color: colors.grid },
                    ticks: {
                        color: colors.text,
                        font: { family: 'Inter', size: 11 }
                    }
                }
            }
        };
    },

    // Create a Followers Line Chart
    createLineChart(canvasId, labels, dataPoints, labelName = 'Followers') {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        
        const colors = this.getThemeColors();
        const options = this.getCommonOptions(colors);
        
        // Gradient fill
        const gradientCtx = ctx.getContext('2d');
        const gradient = gradientCtx.createLinearGradient(0, 0, 0, 300);
        gradient.addColorStop(0, 'rgba(168, 85, 247, 0.3)');
        gradient.addColorStop(1, 'rgba(168, 85, 247, 0)');
        
        return new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: labelName,
                    data: dataPoints,
                    borderColor: colors.primary,
                    borderWidth: 3,
                    backgroundColor: gradient,
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: colors.primary,
                    pointHoverRadius: 7
                }]
            },
            options: options
        });
    },

    // Create a demographics bar/doughnut chart
    createDoughnutChart(canvasId, labels, dataPoints) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        
        const colors = this.getThemeColors();
        
        return new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: dataPoints,
                    backgroundColor: [
                        colors.primary,
                        colors.secondary,
                        colors.info,
                        colors.success,
                        colors.warning
                    ],
                    borderWidth: 1,
                    borderColor: colors.tooltipBorder
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: colors.text,
                            font: { family: 'Inter', size: 12, weight: 500 }
                        }
                    },
                    tooltip: {
                        backgroundColor: colors.tooltipBg,
                        titleColor: colors.text,
                        bodyColor: colors.text,
                        borderColor: colors.tooltipBorder,
                        borderWidth: 1,
                        padding: 12,
                        cornerRadius: 8,
                        titleFont: { family: 'Outfit', size: 14, weight: 600 },
                        bodyFont: { family: 'Inter', size: 13 }
                    }
                }
            }
        });
    },

    // Create double Bar Chart
    createDoubleBarChart(canvasId, labels, data1, label1, data2, label2) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        
        const colors = this.getThemeColors();
        const options = this.getCommonOptions(colors);
        
        return new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: label1,
                        data: data1,
                        backgroundColor: colors.primary,
                        borderRadius: 6
                    },
                    {
                        label: label2,
                        data: data2,
                        backgroundColor: colors.secondary,
                        borderRadius: 6
                    }
                ]
            },
            options: options
        });
    }
};
