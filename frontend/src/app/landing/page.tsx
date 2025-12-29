'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';

export default function LandingPage() {
  const [email, setEmail] = useState('');
  const [agency, setAgency] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    // In production: Send to waitlist API
    await new Promise(resolve => setTimeout(resolve, 1000));

    setSubmitted(true);
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-[#0A0E1A] text-white overflow-hidden">
      {/* Animated Background */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 -left-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute bottom-1/4 -right-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl animate-pulse delay-1000"></div>
        <div className="absolute top-1/2 left-1/2 w-96 h-96 bg-indigo-500/5 rounded-full blur-3xl animate-pulse delay-2000"></div>
      </div>

      {/* Header */}
      <header className="relative z-10 border-b border-blue-500/10 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-6 py-6 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-lg flex items-center justify-center shadow-lg shadow-blue-500/50">
              <svg
                className="w-6 h-6 text-white"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                />
              </svg>
            </div>
            <span className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
              Veritas
            </span>
          </div>
          <div className="text-sm text-gray-400">
            Government Fraud Orchestrator
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <main className="relative z-10">
        <div className="max-w-7xl mx-auto px-6 py-24">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
            {/* Left Column - Content */}
            <div className="space-y-8">
              <div className="inline-flex items-center px-4 py-2 rounded-full border border-blue-500/30 bg-blue-500/5 backdrop-blur-sm">
                <div className="w-2 h-2 bg-blue-400 rounded-full mr-2 animate-pulse"></div>
                <span className="text-sm text-blue-300">AI-Powered Fraud Detection</span>
              </div>

              <h1 className="text-5xl lg:text-7xl font-bold leading-tight">
                Stop Fraud{' '}
                <span className="bg-gradient-to-r from-blue-400 via-cyan-400 to-blue-500 bg-clip-text text-transparent">
                  Before It Starts
                </span>
              </h1>

              <p className="text-xl text-gray-400 leading-relaxed">
                Veritas automates fraud detection for state grant programs using
                AI-powered investigation across physical, corporate, digital, and
                forensic dimensions.
              </p>

              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-2">
                  <div className="text-3xl font-bold text-blue-400">95%</div>
                  <div className="text-sm text-gray-400">Fraud Ring Detection Rate</div>
                </div>
                <div className="space-y-2">
                  <div className="text-3xl font-bold text-cyan-400">60 sec</div>
                  <div className="text-sm text-gray-400">Average Investigation Time</div>
                </div>
                <div className="space-y-2">
                  <div className="text-3xl font-bold text-indigo-400">13 Tools</div>
                  <div className="text-sm text-gray-400">Automated Verification Checks</div>
                </div>
                <div className="space-y-2">
                  <div className="text-3xl font-bold text-purple-400">$4.2M</div>
                  <div className="text-sm text-gray-400">Fraud Prevented (Pilot)</div>
                </div>
              </div>

              {/* Key Features */}
              <div className="space-y-4 pt-8">
                <div className="flex items-start space-x-3">
                  <div className="w-6 h-6 rounded-full bg-blue-500/20 flex items-center justify-center flex-shrink-0 mt-1">
                    <svg className="w-4 h-4 text-blue-400" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div>
                    <div className="font-semibold text-white">Cross-Case Fraud Ring Detection</div>
                    <div className="text-sm text-gray-400">Graph database identifies coordinated fraud networks</div>
                  </div>
                </div>

                <div className="flex items-start space-x-3">
                  <div className="w-6 h-6 rounded-full bg-blue-500/20 flex items-center justify-center flex-shrink-0 mt-1">
                    <svg className="w-4 h-4 text-blue-400" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div>
                    <div className="font-semibold text-white">Document Forensics Kill Switch</div>
                    <div className="text-sm text-gray-400">Automatic detection of Photoshopped bank statements</div>
                  </div>
                </div>

                <div className="flex items-start space-x-3">
                  <div className="w-6 h-6 rounded-full bg-blue-500/20 flex items-center justify-center flex-shrink-0 mt-1">
                    <svg className="w-4 h-4 text-blue-400" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div>
                    <div className="font-semibold text-white">GovCloud Compliant</div>
                    <div className="text-sm text-gray-400">Air-gapped deployment with full audit trail</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column - Waitlist Form */}
            <div className="relative">
              <div className="absolute inset-0 bg-gradient-to-br from-blue-500/20 to-cyan-500/20 rounded-3xl blur-xl"></div>
              <div className="relative bg-[#0F1419] border border-blue-500/20 rounded-2xl p-8 shadow-2xl backdrop-blur-sm">
                {!submitted ? (
                  <>
                    <h2 className="text-2xl font-bold mb-2">Join the Waitlist</h2>
                    <p className="text-gray-400 mb-8">
                      Limited pilot program for state agencies
                    </p>

                    <form onSubmit={handleSubmit} className="space-y-6">
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">
                          State Agency / Department
                        </label>
                        <input
                          type="text"
                          value={agency}
                          onChange={(e) => setAgency(e.target.value)}
                          placeholder="e.g., California Franchise Tax Board"
                          className="w-full px-4 py-3 bg-[#1A1F2E] border border-blue-500/20 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/20"
                          required
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">
                          Work Email
                        </label>
                        <input
                          type="email"
                          value={email}
                          onChange={(e) => setEmail(e.target.value)}
                          placeholder="your.name@agency.gov"
                          className="w-full px-4 py-3 bg-[#1A1F2E] border border-blue-500/20 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/20"
                          required
                        />
                      </div>

                      <Button
                        type="submit"
                        disabled={loading}
                        className="w-full bg-gradient-to-r from-blue-500 to-cyan-500 hover:from-blue-600 hover:to-cyan-600 text-white font-semibold py-3 rounded-lg shadow-lg shadow-blue-500/50 transition-all duration-200 disabled:opacity-50"
                      >
                        {loading ? 'Submitting...' : 'Request Early Access'}
                      </Button>

                      <p className="text-xs text-gray-500 text-center">
                        Priority access for fraud investigation units
                      </p>
                    </form>
                  </>
                ) : (
                  <div className="text-center py-12">
                    <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-full flex items-center justify-center mx-auto mb-4 shadow-lg shadow-blue-500/50">
                      <svg
                        className="w-8 h-8 text-white"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                    </div>
                    <h3 className="text-2xl font-bold mb-2">You're on the list!</h3>
                    <p className="text-gray-400">
                      We'll reach out to {agency} shortly to discuss pilot deployment.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Investigation Layers Showcase */}
        <div className="max-w-7xl mx-auto px-6 py-24">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold mb-4">
              5-Layer{' '}
              <span className="bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
                Investigation Framework
              </span>
            </h2>
            <p className="text-xl text-gray-400">
              Comprehensive fraud detection across every dimension
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
            {[
              {
                layer: 'Layer 1',
                title: 'Physical',
                icon: '🏢',
                description: 'Street View + Property ownership verification',
                tools: 2,
              },
              {
                layer: 'Layer 2',
                title: 'Corporate',
                icon: '📊',
                description: 'Business registry + Domain forensics',
                tools: 3,
              },
              {
                layer: 'Layer 3',
                title: 'Digital Identity',
                icon: '🔍',
                description: 'Phone carrier + Email footprint + Breach history',
                tools: 3,
              },
              {
                layer: 'Layer 4',
                title: 'Forensics',
                icon: '📄',
                description: 'PDF metadata manipulation detection',
                tools: 1,
              },
              {
                layer: 'Layer 5',
                title: 'Intelligence',
                icon: '🕸️',
                description: 'Fraud ring + Plagiarism + Ghost employees',
                tools: 4,
              },
            ].map((item, index) => (
              <div
                key={index}
                className="bg-[#0F1419] border border-blue-500/10 rounded-xl p-6 hover:border-blue-500/30 transition-all duration-300 group"
              >
                <div className="text-4xl mb-4">{item.icon}</div>
                <div className="text-xs text-blue-400 font-semibold mb-1">{item.layer}</div>
                <h3 className="text-xl font-bold mb-2">{item.title}</h3>
                <p className="text-sm text-gray-400 mb-4">{item.description}</p>
                <div className="text-xs text-gray-500">{item.tools} automated tools</div>
              </div>
            ))}
          </div>
        </div>

        {/* Use Cases */}
        <div className="max-w-7xl mx-auto px-6 py-24">
          <h2 className="text-4xl font-bold text-center mb-16">
            Built for{' '}
            <span className="bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
              Government Investigators
            </span>
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {[
              {
                title: 'Grant Application Fraud',
                description: 'Detect shell companies applying for CARES Act, EIDL, and state business grants',
                stat: '89% fraud detection rate',
              },
              {
                title: 'Unemployment Insurance',
                description: 'Identify synthetic identities and deceased claimants in UI benefit applications',
                stat: '47 plagiarized narratives found',
              },
              {
                title: 'Licensing & Permits',
                description: 'Verify contractor credentials and detect document manipulation in permit applications',
                stat: '100% document manipulation caught',
              },
            ].map((useCase, index) => (
              <div
                key={index}
                className="bg-[#0F1419] border border-blue-500/10 rounded-xl p-8 hover:border-blue-500/30 transition-all"
              >
                <h3 className="text-xl font-bold mb-3">{useCase.title}</h3>
                <p className="text-gray-400 mb-6">{useCase.description}</p>
                <div className="text-sm text-blue-400 font-semibold">{useCase.stat}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer CTA */}
        <div className="max-w-4xl mx-auto px-6 py-24 text-center">
          <h2 className="text-4xl font-bold mb-6">
            Ready to protect your state's funding?
          </h2>
          <p className="text-xl text-gray-400 mb-8">
            Join agencies already using AI to stop fraud before it happens.
          </p>
          <a
            href="#top"
            className="inline-block bg-gradient-to-r from-blue-500 to-cyan-500 hover:from-blue-600 hover:to-cyan-600 text-white font-semibold px-8 py-4 rounded-lg shadow-lg shadow-blue-500/50 transition-all"
          >
            Request Demo Access
          </a>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-blue-500/10 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-6 py-8">
          <div className="flex flex-col md:flex-row justify-between items-center text-sm text-gray-500">
            <div className="mb-4 md:mb-0">
              © 2024 Veritas GFO. Government Use Only.
            </div>
            <div className="flex space-x-6">
              <a href="#" className="hover:text-blue-400 transition-colors">Documentation</a>
              <a href="#" className="hover:text-blue-400 transition-colors">Security</a>
              <a href="#" className="hover:text-blue-400 transition-colors">Compliance</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
