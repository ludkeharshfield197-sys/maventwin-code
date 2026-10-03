package org.maventwin.observer;
import java.io.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.apache.maven.AbstractMavenLifecycleParticipant;
import org.apache.maven.execution.MavenSession;
import org.apache.maven.project.MavenProject;
import org.apache.maven.model.io.xpp3.MavenXpp3Writer;
import org.apache.maven.lifecycle.MavenExecutionPlan;
import org.apache.maven.lifecycle.internal.LifecycleTask;
import org.apache.maven.lifecycle.internal.LifecycleExecutionPlanCalculator;
import org.apache.maven.plugin.MojoExecution;
/** Calculates plans after all afterProjectsRead callbacks and the measurement goal. Never executes the planned phase. */
public class ObserverLate extends AbstractMavenLifecycleParticipant {
  public LifecycleExecutionPlanCalculator calculator;
  private String cell(Object x){return x==null?"":x.toString().replace("\t"," ").replace("\r"," ").replace("\n"," ");}
  private void capture(MavenSession session,boolean finished) {
    String target=System.getProperty("maventwin.observer.output");if(target==null || session.getProjects()==null)return;
    try {
      Path dir=Paths.get(target);Files.createDirectories(dir);int i=0;
      for(MavenProject project:session.getProjects()) {
        String stem=String.format("%03d",i++);
        try(Writer w=Files.newBufferedWriter(dir.resolve(stem+(finished?"-final-model.xml":"-model.xml")),StandardCharsets.UTF_8)) {new MavenXpp3Writer().write(w,project.getModel());}
        if(!finished)continue;
        MavenProject previous=session.getCurrentProject();session.setCurrentProject(project);
        try {
          LifecycleExecutionPlanCalculator selected=calculator;
          if(selected==null && session.getContainer()!=null)selected=session.getContainer().lookup(LifecycleExecutionPlanCalculator.class);
          if(selected==null)throw new IllegalStateException("LifecycleExecutionPlanCalculator injection unavailable");
          List<Object> tasks=new ArrayList<>();tasks.add(new LifecycleTask(System.getProperty("maventwin.observer.phase","package")));
          MavenExecutionPlan plan=selected.calculateExecutionPlan(session,project,tasks,false);
          try(BufferedWriter w=Files.newBufferedWriter(dir.resolve(stem+"-plan.tsv"),StandardCharsets.UTF_8)) {
            w.write("order\tgroupId\tartifactId\tversion\texecutionId\tgoal\tphase\tsource\tconfiguration\n");int n=0;
            for(MojoExecution m:plan.getMojoExecutions())w.write((n++)+"\t"+cell(m.getGroupId())+"\t"+cell(m.getArtifactId())+"\t"+cell(m.getVersion())+"\t"+cell(m.getExecutionId())+"\t"+cell(m.getGoal())+"\t"+cell(m.getLifecyclePhase())+"\t"+cell(m.getSource())+"\t"+cell(m.getConfiguration())+"\n");
          }
          Files.writeString(dir.resolve(stem+"-plan-status.txt"),"CALCULATED_NOT_EXECUTED_AFTER_MEASUREMENT_GOAL\n",StandardCharsets.UTF_8);
        } catch(Exception e){try(PrintWriter w=new PrintWriter(Files.newBufferedWriter(dir.resolve(stem+"-plan-error.txt"),StandardCharsets.UTF_8))){e.printStackTrace(w);}}
        finally{session.setCurrentProject(previous);}
      }
    }catch(Exception e){System.err.println("MAVENTWIN_OBSERVER_FAILURE: "+e);}
  }
  @Override public void afterProjectsRead(MavenSession session){capture(session,false);}
  @Override public void afterSessionEnd(MavenSession session){capture(session,true);}
}
